import os
import json
import re
import math
from flask import current_app

# Try importing the standard RAG libraries. If they fail, we will use the fallback.
try:
    import chromadb
    from langchain_community.embeddings import HuggingFaceEmbeddings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

class FallbackVectorStore:
    def __init__(self, db_dir):
        self.db_dir = db_dir
        self.file_path = os.path.join(db_dir, "fallback_vector_store.json")
        os.makedirs(db_dir, exist_ok=True)
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save fallback vector store: {e}")

    def add_chunks(self, paper_id: str, chunks: list):
        self.data[str(paper_id)] = chunks
        self.save()

    def query(self, query: str, top_k: int = 4, paper_ids: list = None):
        query_words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 2]
        if not query_words:
            query_words = query.lower().split()

        candidates = []
        for pid, chunks in self.data.items():
            if paper_ids and str(pid) not in [str(x) for x in paper_ids]:
                continue
            for chunk in chunks:
                chunk_lower = chunk.lower()
                # Simple TF-IDF score
                score = 0
                for word in query_words:
                    count = chunk_lower.count(word)
                    if count > 0:
                        score += (1 + math.log(count)) * (1.0 / (chunk_lower.count(word) + 1)) # standard term weighting
                        # Add weight if word matches exactly as word token
                        if re.search(r'\b' + re.escape(word) + r'\b', chunk_lower):
                            score += 2.0
                if score > 0:
                    candidates.append((score, chunk))

        # If no candidates match terms, return some arbitrary chunks from the papers to maintain context
        if not candidates:
            for pid, chunks in self.data.items():
                if paper_ids and str(pid) not in [str(x) for x in paper_ids]:
                    continue
                for chunk in chunks[:top_k]:
                    candidates.append((0.1, chunk))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:top_k]]


class VectorStoreManager:
    def __init__(self):
        self.use_fallback = not CHROMA_AVAILABLE
        self.embeddings = None
        self.chroma_client = None

        if not self.use_fallback:
            try:
                # Try setting up embedding model
                # Set local cache dir to avoid writing to C:\Users or elsewhere if problematic
                self.embeddings = HuggingFaceEmbeddings(model_name=r".\models\all-MiniLM-L6-v2")
            except Exception as e:
                print(f"Warning: sentence-transformers failed to load, falling back to keyword search: {e}")
                self.use_fallback = True

    def get_client(self):
        chroma_path = current_app.config['CHROMA_DB_DIR']
        if self.use_fallback:
            return FallbackVectorStore(chroma_path)
        
        try:
            if not self.chroma_client:
                self.chroma_client = chromadb.PersistentClient(path=chroma_path)
            return self.chroma_client
        except Exception as e:
            print(f"Warning: ChromaDB client failure, switching to fallback: {e}")
            self.use_fallback = True
            return FallbackVectorStore(chroma_path)

    def add_paper_chunks(self, paper_id: int, chunks: list):
        client = self.get_client()
        if self.use_fallback:
            client.add_chunks(str(paper_id), chunks)
            return

        try:
            collection = client.get_or_create_collection(name="scientific_papers")
            ids = [f"paper_{paper_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"paper_id": str(paper_id)} for _ in chunks]
            embeddings_list = self.embeddings.embed_documents(chunks)
            
            collection.add(
                ids=ids,
                embeddings=embeddings_list,
                documents=chunks,
                metadatas=metadatas
            )
        except Exception as e:
            print(f"Failed to add to ChromaDB collection, using fallback: {e}")
            # Try to recover using fallback vector store
            fallback = FallbackVectorStore(current_app.config['CHROMA_DB_DIR'])
            fallback.add_chunks(str(paper_id), chunks)

    def query_similar(self, query: str, top_k: int = 4, paper_ids: list = None):
        client = self.get_client()
        if self.use_fallback or isinstance(client, FallbackVectorStore):
            return client.query(query, top_k=top_k, paper_ids=paper_ids)

        try:
            collection = client.get_or_create_collection(name="scientific_papers")
            query_embedding = self.embeddings.embed_query(query)
            where_filter = {}
            if paper_ids:
                if len(paper_ids) == 1:
                    where_filter = {"paper_id": str(paper_ids[0])}
                else:
                    where_filter = {"paper_id": {"$in": [str(pid) for pid in paper_ids]}}
                
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter if paper_ids else None
            )
            return results['documents'][0] if results and results['documents'] else []
        except Exception as e:
            print(f"Querying ChromaDB failed, using fallback query: {e}")
            fallback = FallbackVectorStore(current_app.config['CHROMA_DB_DIR'])
            return fallback.query(query, top_k=top_k, paper_ids=paper_ids)