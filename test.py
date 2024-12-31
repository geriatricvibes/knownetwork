from neo4j import GraphDatabase
from typing import List, Dict, Any

class Neo4jBookGraph:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def create_character(self, name: str, attributes: Dict[str, Any]):
        with self.driver.session() as session:
            session.run("""
                MERGE (c:Character {name: $name})
                SET c += $attributes
                """, name=name, attributes=attributes)

    def create_location(self, name: str, attributes: Dict[str, Any]):
        with self.driver.session() as session:
            session.run("""
                MERGE (l:Location {name: $name})
                SET l += $attributes
                """, name=name, attributes=attributes)

    def create_relationship(self, from_name: str, to_name: str, relationship_type: str, properties: Dict[str, Any] = {}):
        with self.driver.session() as session:
            # Replace spaces with underscores in relationship type
            relationship_type = relationship_type.replace(" ", "_").upper()
            query = f"""
                MATCH (a) WHERE a.name = $from_name
                MATCH (b) WHERE b.name = $to_name
                MERGE (a)-[r:{relationship_type}]->(b)
                SET r += $properties
                """
            session.run(query, 
                       from_name=from_name, 
                       to_name=to_name, 
                       properties=properties)

    def find_inconsistencies(self):
        # Example query to find potential inconsistencies
        with self.driver.session() as session:
            return session.run("""
                // Add your inconsistency detection queries here
                // For example, characters in two places at once:
                MATCH (c:Character)-[r1:APPEARS_IN]->(l1:Location)
                MATCH (c)-[r2:APPEARS_IN]->(l2:Location)
                WHERE l1 <> l2 AND r1.chapter = r2.chapter
                RETURN c.name, l1.name, l2.name, r1.chapter
                """)

# Usage example
if __name__ == "__main__":
    graph = Neo4jBookGraph(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="rrttyy4444"
    )
    
    try:
        # Example usage with LLM-extracted information
        character_info = {
            "age": 25,
            "description": "Brave warrior",
            "first_appearance": "Chapter 1"
        }
        graph.create_character("John Snow", character_info)
        
        location_info = {
            "type": "castle",
            "description": "Northern fortress"
        }
        graph.create_location("Winterfell", location_info)
        
        # Create relationship with properties
        graph.create_relationship(
            "John Snow", "Winterfell", "APPEARS_IN",
            {"chapter": 1, "context": "Lives here"}
        )
        
    finally:
        graph.close()
