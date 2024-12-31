import os
from typing import Dict, Any
import json
import logging
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from dotenv import load_dotenv
import yaml
from neo4j_handler import Neo4jHandler

load_dotenv()

class BookProcessor:
    def __init__(self):
        # Load all prompts
        self.extraction_prompt = self._load_prompt("extraction_prompt.yaml")
        self.entity_details_prompt = self._load_prompt("entity_details_prompt.yaml")
        self.relationship_prompt = self._load_prompt("relationship_prompt.yaml")
        self.timeline_prompt = self._load_prompt("timeline_prompt.yaml")

        # Initialize LangChain chat model
        self.llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("QWEN"),
            model_name="qwen/qwen-2.5-72b-instruct",
            temperature=0.1
        )
        
        # Create output parser
        self.parser = JsonOutputParser()
        
        # Create three separate chains
        self.extraction_chain = self._create_extraction_chain()
        self.entity_details_chain = self._create_entity_details_chain()
        self.relationship_chain = self._create_relationship_chain()
        self.timeline_chain = self._create_timeline_chain()

        self.neo4j_handler = Neo4jHandler()

    def _load_prompt(self, prompt_file: str) -> str:
        """Load prompt from the prompts directory"""
        prompt_path = os.path.join("prompts", prompt_file)
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_data = yaml.safe_load(f)
                return prompt_data['prompt']
        except Exception as e:
            logging.error(f"Error loading prompt file {prompt_file}: {str(e)}")
            raise

    def _create_extraction_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.extraction_prompt),
            ("user", "{chapter_text}")
        ])
        
        # Add JSON formatting instructions and error handling
        return (
            prompt 
            | self.llm.bind(response_format={"type": "json"})  # Explicitly request JSON
            | self.parser.bind(strict=False)  # Make parser more lenient
        )

    def _create_entity_details_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.entity_details_prompt),
            ("user", "Chapter text: {chapter_text}\nFirst pass entities: {entities}")
        ])
        return prompt | self.llm | self.parser

    def _create_relationship_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.relationship_prompt),
            ("user", "Chapter text: {chapter_text}\nEntities found: {entities}")
        ])
        return prompt | self.llm | self.parser

    def _create_timeline_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.timeline_prompt),
            ("user", "Chapter text: {chapter_text}\nEntities found: {entities}")
        ])
        return prompt | self.llm | self.parser

    async def extract_chapter_data(self, chapter_text: str, chapter_number: int):
        try:
            output_dir = "chapter_data"
            os.makedirs(output_dir, exist_ok=True)
            
            print(f"\n=== Processing Chapter {chapter_number} ===")
            print("Step 1/4: Extracting basic entities...")
            first_pass_result = await self.extraction_chain.ainvoke({"chapter_text": chapter_text})
            print(f"✓ Found {len(first_pass_result['entities'])} entities")
            
            # Save first pass results
            with open(os.path.join(output_dir, f"chapter_{chapter_number}_entities.json"), 'w', encoding='utf-8') as f:
                json.dump(first_pass_result, f, indent=2)
            
            print("Step 1b: Saving entities to Neo4j...")
            self.neo4j_handler.save_entities(chapter_number, first_pass_result)
            print("✓ Entities saved to database")
            
            # Extract just the essential entity information
            simplified_entities = [
                {
                    "name": entity["name"],
                    "type": entity["type"],
                    "aliases": entity["aliases"]
                }
                for entity in first_pass_result["entities"]
            ]
            
            print("\nStep 2/4: Extracting detailed entity information...")
            entity_details = await self.entity_details_chain.ainvoke({
                "chapter_text": chapter_text,
                "entities": json.dumps(simplified_entities)
            })
            print("✓ Entity details extracted")
            
            print("Step 2b: Saving entity details to Neo4j...")
            self.neo4j_handler.save_entity_details(chapter_number, entity_details)
            print("✓ Entity details saved to database")
            
            print("\nStep 3/4: Analyzing relationships between entities...")
            relationships = await self.relationship_chain.ainvoke({
                "chapter_text": chapter_text,
                "entities": json.dumps(simplified_entities)
            })
            print(f"✓ Found {len(relationships.get('relationships', []))} relationships")
            
            print("Step 3b: Saving relationships to Neo4j...")
            self.neo4j_handler.save_relationships(chapter_number, relationships)
            print("✓ Relationships saved to database")
            
            print("\nStep 4/4: Extracting timeline and events...")
            timeline = await self.timeline_chain.ainvoke({
                "chapter_text": chapter_text,
                "entities": json.dumps(simplified_entities)
            })
            print(f"✓ Extracted {len(timeline.get('events', []))} timeline events")
            
            print("Step 4b: Saving timeline to Neo4j...")
            self.neo4j_handler.save_timeline(chapter_number, timeline)
            print("✓ Timeline saved to database")
            
            print("\n=== Chapter Processing Complete ===")
            print(f"✓ All data saved for Chapter {chapter_number}")
            print("=====================================\n")
            
            return {
                "basicEntities": first_pass_result,
                "entityDetails": entity_details,
                "relationships": relationships,
                "timeline": timeline
            }
            
        except Exception as e:
            print(f"\n❌ Error processing Chapter {chapter_number}: {str(e)}")
            logging.error(f"Chapter {chapter_number}: Error in extract_chapter_data: {str(e)}")
            raise

    async def process_chapter(self, chapter_text: str, chapter_number: int):
        """Process a chapter and save the extracted data to a JSON file"""
        try:
            # Extract data using LLM
            extracted_data = await self.extract_chapter_data(chapter_text, chapter_number)
            
            # Create output directory if it doesn't exist
            output_dir = "chapter_data"
            os.makedirs(output_dir, exist_ok=True)
            
            # Save to JSON file
            output_file = os.path.join(output_dir, f"chapter_{chapter_number}.json")
            logging.info(f"Chapter {chapter_number}: Saving data to {output_file}")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=2)
            
            logging.info(f"Chapter {chapter_number}: Successfully saved data to file")
            
        except Exception as e:
            logging.error(f"Chapter {chapter_number}: Error processing chapter: {str(e)}")
            raise

    def __del__(self):
        """Cleanup Neo4j connection when object is destroyed"""
        if hasattr(self, 'neo4j_handler'):
            self.neo4j_handler.close()

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='book_processor.log'
    )

    async def main():
        processor = BookProcessor()
        try:
            file_path = 'sample1.txt'
            logging.info(f"Attempting to read file: {file_path}")
            
            if not os.path.exists(file_path):
                logging.error(f"File not found: {file_path}")
                raise FileNotFoundError(f"File not found: {file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as file:
                chapter_text = file.read()
                
            if not chapter_text:
                logging.error("File was empty")
                raise ValueError("File was empty")
                
            logging.info(f"Successfully read file. Content length: {len(chapter_text)}")
            
            await processor.process_chapter(chapter_text, chapter_number=1)
            
        except Exception as e:
            logging.error(f"Main execution error: {str(e)}", exc_info=True)

    asyncio.run(main()) 