import logging
from qdrant_client import QdrantClient
import os
from qdrant_client.http.models import PointStruct, VectorParams, Distance
from sentence_transformers import SentenceTransformer
from PyPDF2 import PdfReader
import uuid
import json

class RAGKBProcessor:
    def __init__(self, collection_name="knowledge_base", recreate_collection=True):
        self.collection_name = collection_name
        self.qdrant_client = QdrantClient(url="http://localhost:6333")  # Connect to Qdrant
        self.st_model = SentenceTransformer('all-MiniLM-L6-v2')  # Pre-trained model

        # Recreate the collection every time the server starts
        if recreate_collection:
            self.reset_collection()  # Ensures clean start
        else:
            logging.warning(f"Using existing collection: {self.collection_name}")

    def reset_collection(self):
        """
        Delete and recreate the Qdrant collection to clear previous data.
        This ensures no data carryover between requests.
        """
        try:
            # Delete existing collection
            self.qdrant_client.delete_collection(collection_name=self.collection_name)
            logging.info(f"Deleted existing collection: {self.collection_name}")
        except Exception as e:
            logging.warning(f"Collection {self.collection_name} does not exist. Proceeding to create it.")

        # Recreate the collection
        self.qdrant_client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        logging.info(f"Recreated collection: {self.collection_name}")

    def vectorize_data(self, data, source, metadata):
        """
        Vectorize text data and add it to Qdrant.
        """
        try:
            points = []
            chunks = self.chunk_text(data)  # Split text into smaller chunks

            for i, chunk in enumerate(chunks):
                # Encode the chunk and add it to Qdrant
                embedding = self.st_model.encode(chunk).tolist()
                points.append(PointStruct(
                    id=i,
                    vector=embedding,
                    payload={"text": chunk, "source": source, "metadata": metadata}
                ))

            # Insert points into Qdrant
            self.qdrant_client.upsert(collection_name=self.collection_name, points=points)
            logging.info(f"Data vectorized successfully with {len(points)} chunks.")
        except Exception as e:
            logging.error(f"Error vectorizing data: {e}")

    def search_context(self, query, top_k=3):
        """
        Search for similar contexts in Qdrant based on query.
        """
        try:
            # Encode query text into embeddings
            query_vector = self.st_model.encode(query).tolist()

            # Search Qdrant
            results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=top_k,
            )
            return [res.payload for res in results]
        except Exception as e:
            logging.error(f"Error searching context: {e}")
            return []

    def chunk_text(self, text, chunk_size=500):
        """
        Split text into smaller chunks for processing.
        """
        chunks = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])
        return chunks

    def process_transcripts(self, transcripts):
        """Processes JSON transcripts and stores chunks in the Qdrant collection."""
        for transcript in transcripts:
            text = json.dumps(transcript, indent=2)
            chunks = self.chunk_text(text)
            self.all_chunks.extend(chunks)  # Collect chunks for TF-IDF

            # Prepare points for Qdrant
            points = []
            for chunk_id, chunk in enumerate(chunks):
                embedding = self.st_model.encode(chunk).tolist()
                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=embedding,
                        payload={
                            "text": chunk,
                            "chunk_id": chunk_id,
                            "source": "transcripts",
                            "metadata": {
                                "id": transcript["id"],
                                "title": transcript["title"],
                                "date": transcript["date"],
                                "attendees": [att["email"] for att in transcript.get("meeting_attendees", [])],
                            }
                        }
                    )
                )

            # Upload points to Qdrant
            self.qdrant_client.upsert(collection_name=self.collection_name, points=points)
            # print(f"Processed {len(chunks)} chunks for transcript ID {transcript['id']}")

    def process_pdfs_in_folder(self, folder_path):
        """Processes all PDFs in a folder and stores chunks in the Qdrant collection."""
        for filename in os.listdir(folder_path):
            if filename.endswith(".pdf"):
                pdf_path = os.path.join(folder_path, filename)
                self.process_pdf(pdf_path)

    def process_pdf(self, pdf_path):
        """Processes a single PDF file and stores chunks in the Qdrant collection."""
        reader = PdfReader(pdf_path)
        for page_number, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text.strip():  # Skip empty pages
                continue
            chunks = self.chunk_text(text)
            self.all_chunks.extend(chunks)  # Collect chunks for TF-IDF

            # Prepare points for Qdrant
            points = []
            for chunk_id, chunk in enumerate(chunks):
                embedding = self.st_model.encode(chunk).tolist()
                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=embedding,
                        payload={
                            "text": chunk,
                            "chunk_id": chunk_id,
                            "source": "pdf",
                            "metadata": {
                                "pdf_name": os.path.basename(pdf_path),
                                "page": page_number + 1,
                            }
                        }
                    )
                )

            # Upload points to Qdrant
            self.qdrant_client.upsert(collection_name=self.collection_name, points=points)
        # print(f"Processed PDF: {os.path.basename(pdf_path)}")

    def search_context(self, query, top_k=3):
        """Searches the knowledge base for relevant chunks based on a query."""
        query_vector = self.st_model.encode(query).tolist()
        results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
        )

        contexts = []
        for result in results:
            payload = result.payload
            contexts.append({
                "score": result.score,
                "text": payload.get("text"),
                "source": payload.get("source"),
                "metadata": payload.get("metadata"),
            })
        return contexts
