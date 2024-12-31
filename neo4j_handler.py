from neo4j import GraphDatabase
from typing import Dict, List
import logging
from dotenv import load_dotenv
import os

load_dotenv()

class Neo4jHandler:
    def __init__(self):
        self.uri = "bolt://localhost:7687"
        self.user = "neo4j"
        self.password = "rrttyy4444"
        
        logging.info(f"Attempting to connect to Neo4j at {self.uri}")
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Verify connection
            self.driver.verify_connectivity()
            logging.info("Successfully connected to Neo4j")
        except Exception as e:
            logging.error(f"Failed to connect to Neo4j: {str(e)}")
            raise

    def close(self):
        try:
            self.driver.close()
            logging.info("Neo4j connection closed successfully")
        except Exception as e:
            logging.error(f"Error closing Neo4j connection: {str(e)}")

    def save_entities(self, chapter_number: int, entities_data: Dict):
        """
        Save the first-pass entities data to Neo4j
        """
        logging.info(f"Attempting to save entities for chapter {chapter_number}")
        logging.debug(f"Entities data: {entities_data}")
        
        with self.driver.session() as session:
            try:
                # Create constraints if they don't exist
                logging.info("Creating constraints...")
                session.execute_write(self._create_constraints)
                
                # Save entities
                logging.info(f"Saving {len(entities_data['entities'])} entities...")
                session.execute_write(
                    self._create_entities, 
                    chapter_number=chapter_number,
                    entities=entities_data["entities"]
                )
                
                logging.info(f"Successfully saved entities for chapter {chapter_number} to Neo4j")
                
            except Exception as e:
                logging.error(f"Error saving to Neo4j: {str(e)}")
                raise

    def save_entity_details(self, chapter_number: int, entity_details_data: Dict):
        """
        Save the second-pass entity details data to Neo4j
        """
        logging.info(f"Attempting to save entity details for chapter {chapter_number}")
        logging.debug(f"Entity details data: {entity_details_data}")
        
        with self.driver.session() as session:
            try:
                session.execute_write(
                    self._update_entity_details,
                    chapter_number=chapter_number,
                    entity_details=entity_details_data["entityDetails"]
                )
                logging.info(f"Successfully saved entity details for chapter {chapter_number}")
            except Exception as e:
                logging.error(f"Error saving entity details to Neo4j: {str(e)}")
                raise

    def save_relationships(self, chapter_number: int, relationships_data: Dict):
        """
        Save the relationship data to Neo4j
        """
        logging.info(f"Attempting to save relationships for chapter {chapter_number}")
        logging.debug(f"Relationships data: {relationships_data}")
        
        with self.driver.session() as session:
            try:
                session.execute_write(
                    self._create_relationships,
                    chapter_number=chapter_number,
                    relationships=relationships_data["relationships"]
                )
                logging.info(f"Successfully saved relationships for chapter {chapter_number}")
            except Exception as e:
                logging.error(f"Error saving relationships to Neo4j: {str(e)}")
                raise

    def save_timeline(self, chapter_number: int, timeline_data: Dict):
        """
        Save the timeline/events data to Neo4j and create sequential relationships
        """
        logging.info(f"Attempting to save timeline for chapter {chapter_number}")
        logging.debug(f"Timeline data: {timeline_data}")
        
        with self.driver.session() as session:
            try:
                session.execute_write(
                    self._create_timeline_events,
                    chapter_number=chapter_number,
                    events=timeline_data["events"]
                )
                logging.info(f"Successfully saved timeline for chapter {chapter_number}")
            except Exception as e:
                logging.error(f"Error saving timeline to Neo4j: {str(e)}")
                raise

    @staticmethod
    def _create_constraints(tx):
        """Create unique constraints for entities"""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE (e.name, e.chapter) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Alias) REQUIRE (a.name, a.chapter) IS UNIQUE"
        ]
        
        for constraint in constraints:
            try:
                logging.info(f"Executing constraint: {constraint}")
                tx.run(constraint)
            except Exception as e:
                logging.warning(f"Constraint creation warning: {str(e)}")
                continue

    @staticmethod
    def _create_entities(tx, chapter_number: int, entities: List[Dict]):
        # Create Chapter node and connect it sequentially
        tx.run("""
            MERGE (c:Chapter {name: 'Ch ' + toString($chapter)})
            SET c.number = $chapter,
                c.timestamp = datetime(),
                c.label = 'Ch ' + toString($chapter)
            WITH c
            OPTIONAL MATCH (prev:Chapter {number: $prevChapter})
            WITH c, prev
            WHERE prev IS NOT NULL
            MERGE (prev)-[:NEXT]->(c)
        """, chapter=chapter_number, prevChapter=chapter_number-1)

        for entity in entities:
            try:
                # Modified to create chapter-specific entities
                tx.run("""
                    CREATE (e:Entity {
                        name: $name,
                        type: $type,
                        chapter: $chapter
                    })
                    WITH e
                    MATCH (c:Chapter {number: $chapter})
                    CREATE (c)-[:CONTAINS]->(e)
                """, name=entity["name"], type=entity["type"], chapter=chapter_number)

                # Modified alias creation to be chapter-specific
                for alias in entity["aliases"]:
                    tx.run("""
                        CREATE (a:Alias {
                            name: $alias,
                            chapter: $chapter
                        })
                        MATCH (e:Entity {name: $entity_name, chapter: $chapter})
                        CREATE (a)-[r:REFERS_TO]->(e)
                        WITH a
                        MATCH (c:Chapter {number: $chapter})
                        CREATE (c)-[:CONTAINS]->(a)
                    """, alias=alias, entity_name=entity["name"], chapter=chapter_number)

                # Modified mentions to only connect to entities
                for mention in entity["mentions"]:
                    tx.run("""
                        MATCH (e:Entity {name: $entity_name})
                        CREATE (m:Mention {
                            text: $text, 
                            timestamp: datetime()
                        })
                        CREATE (m)-[:MENTIONS]->(e)
                    """, entity_name=entity["name"], 
                        text=mention["textExcerpt"])
            except Exception as e:
                logging.error(f"Error processing entity {entity['name']}: {str(e)}")
                raise

    @staticmethod
    def _update_entity_details(tx, chapter_number: int, entity_details: List[Dict]):
        # Ensure Chapter node exists
        tx.run("""
            MERGE (c:Chapter {name: 'Ch ' + toString($chapter)})
            SET c.number = $chapter,
                c.timestamp = datetime(),
                c.label = 'Ch ' + toString($chapter)
        """, chapter=chapter_number)

        for detail in entity_details:
            try:
                logging.debug(f"Updating details for entity: {detail['name']}")
                
                # Updated query to only connect details to entity
                query = """
                MATCH (e:Entity {name: $name})
                CREATE (cd:ChapterDetails {
                    chapter: $chapter,
                    description: $description,
                    physicalTraits: $physical,
                    roleInChapter: $role,
                    motivations: $motivations,
                    status: $status,
                    notes: $notes,
                    timestamp: datetime()
                })
                CREATE (e)-[:HAS_DETAILS_IN]->(cd)
                """

                tx.run(
                    query,
                    name=detail["name"],
                    description=detail.get("description", "Unknown"),
                    physical=detail.get("physicalTraits", "Unknown"),
                    abilities=detail.get("abilities", []),
                    role=detail.get("roleInChapter", "Unknown"),
                    motivations=detail.get("motivations", "Unknown"),
                    status=detail.get("status", "Unknown"),
                    notes=detail.get("notes", "Unknown"),
                    chapter=chapter_number
                )
                
                # If abilities are present, create individual Ability nodes
                if "abilities" in detail and detail["abilities"]:
                    for ability in detail["abilities"]:
                        # Fixed query with proper WITH clause
                        ability_query = """
                        MERGE (a:Ability {name: $ability})
                        WITH a
                        MATCH (e:Entity {name: $entity_name})
                        MERGE (e)-[r:HAS_ABILITY]->(a)
                        SET r.firstSeenInChapter = 
                            CASE 
                                WHEN r.firstSeenInChapter IS NULL 
                                THEN $chapter 
                                ELSE r.firstSeenInChapter 
                            END
                        """
                        
                        tx.run(
                            ability_query,
                            ability=ability,
                            entity_name=detail["name"],
                            chapter=chapter_number
                        )
                
            except Exception as e:
                logging.error(f"Error processing details for entity {detail['name']}: {str(e)}")
                raise

    @staticmethod
    def _create_relationships(tx, chapter_number: int, relationships: List[Dict]):
        # Modified to work with chapter-specific entities
        for rel in relationships:
            try:
                query = f"""
                MATCH (from:Entity {{name: $from_entity, chapter: $chapter}})
                MATCH (to:Entity {{name: $to_entity, chapter: $chapter}})
                CREATE (from)-[r:{rel['relationshipType']} {{
                    chapter: $chapter,
                    contextExcerpts: [$context]
                }}]->(to)
                """
                
                tx.run(
                    query,
                    from_entity=rel["fromEntity"],
                    to_entity=rel["toEntity"],
                    context=rel["contextExcerpt"],
                    chapter=chapter_number
                )

            except Exception as e:
                logging.error(f"Error processing relationship between {rel['fromEntity']} and {rel['toEntity']}: {str(e)}")
                raise

    @staticmethod
    def _create_timeline_events(tx, chapter_number: int, events: List[Dict]):
        # Ensure Chapter node exists
        tx.run("""
            MERGE (c:Chapter {name: 'Ch ' + toString($chapter)})
            SET c.number = $chapter,
                c.timestamp = datetime(),
                c.label = 'Ch ' + toString($chapter)
        """, chapter=chapter_number)
        
        # Create events and link them sequentially
        for idx, event in enumerate(events):
            try:
                # Create the event node and connect to chapter
                query = """
                MATCH (c:Chapter {number: $chapter})
                CREATE (e:Event {
                    name: $name,
                    timeReference: $timeRef,
                    location: $location,
                    outcome: $outcome,
                    contextExcerpt: $context,
                    sequenceNumber: $seq,
                    timestamp: datetime()
                })
                CREATE (c)-[:HAS_EVENT]->(e)
                
                // Connect to previous event if it exists
                WITH e, c
                OPTIONAL MATCH (c)-[:HAS_EVENT]->(prev:Event {sequenceNumber: $prevSeq})
                WITH e, prev
                WHERE prev IS NOT NULL
                CREATE (prev)-[:NEXT_EVENT]->(e)
                """
                
                tx.run(
                    query,
                    chapter=chapter_number,
                    name=event["name"],
                    timeRef=event.get("timeReference", "Unknown"),
                    location=event.get("location", "Unknown"),
                    outcome=event["outcome"],
                    context=event["contextExcerpt"],
                    seq=idx,
                    prevSeq=idx-1
                )
                
                # Connect event to participating entities
                if "participants" in event and event["participants"]:
                    for participant in event["participants"]:
                        tx.run("""
                            MATCH (e:Event {name: $event_name})
                            MATCH (p:Entity {name: $participant})
                            CREATE (e)-[:INVOLVES]->(p)
                        """, event_name=event["name"], participant=participant)
                    
            except Exception as e:
                logging.error(f"Error processing event {event['name']}: {str(e)}")
                raise

if __name__ == "__main__":
    # Set up logging FIRST - before any other operations
    logging.basicConfig(
        level=logging.DEBUG,  # Show all log levels
        format='%(asctime)s - %(levelname)s - %(message)s',
        force=True  # This ensures our configuration takes precedence
    )

    # Add an initial log message to verify logging is working
    logging.info("Starting Neo4j relationship test")
    
    handler = None
    try:
        # Test connection
        logging.info("Attempting to create Neo4jHandler...")
        handler = Neo4jHandler()
        logging.info("Neo4jHandler created successfully")
        
        # Test relationship data
        test_data = {
            "relationships": [
                {
                    "fromEntity": "Character A",
                    "toEntity": "Character B",
                    "relationshipType": "FRIEND_OF",
                    "contextExcerpt": "Character A and Character B were seen laughing together"
                },
                {
                    "fromEntity": "Character A",
                    "toEntity": "Location X",
                    "relationshipType": "LIVES_IN",
                    "contextExcerpt": "Character A resided in Location X"
                }
            ]
        }
        
        # First create the entities that will be related
        entity_data = {
            "entities": [
                {
                    "name": "Character A",
                    "type": "Character",
                    "aliases": [],
                    "mentions": [{"textExcerpt": "Test mention"}]
                },
                {
                    "name": "Character B",
                    "type": "Character",
                    "aliases": [],
                    "mentions": [{"textExcerpt": "Test mention"}]
                },
                {
                    "name": "Location X",
                    "type": "Location",
                    "aliases": [],
                    "mentions": [{"textExcerpt": "Test mention"}]
                }
            ]
        }
        
        # Save entities first
        logging.info("Creating test entities...")
        handler.save_entities(1, entity_data)
        
        # Then try to save relationships
        logging.info("Attempting to save test relationships...")
        handler.save_relationships(1, test_data)
        logging.info("Test relationships saved successfully")
        
    except Exception as e:
        logging.error(f"Test failed with error: {str(e)}", exc_info=True)
    finally:
        if handler:
            logging.info("Closing Neo4j connection...")
            handler.close()
        logging.info("Test complete")