from .retrieve import Retrieve
from quest.utils import *
from quest.core.datapack import *
import quest.conf.settings as settings
import numpy as np
from quest.core.nlp.text_cluster import faiss_kmeans_clustering


class RetrieveText(Retrieve):
    """
    Info : columns - a list of ColumnExpr
            table - the retrieve tableName
            type - the retrieve type ('Photo'/'Text'/..)

            self.retreieveList
            self.indexer
            self.sampler
    Input : None
    """
    def __init__(self, columns, table, type):
        super().__init__(columns, table, type)
        self.name = 'RetrieveText'

    def process(self):
        
        # {doc_id1 : { column1 :[text1, text2, ...], }
        
        # CRITICAL: Clear output from previous query execution
        # This prevents state leakage between multiple query runs
        self.output = []

        columns = column_util.parse_full(self.columns) # [U.a1, U.a2, V.a1]
        
        print(f"[DEBUG RetrieveText] Processing retrieve for columns: {columns}")
        print(f"[DEBUG RetrieveText] retrieveList size: {len(self.retrieveList)}")
        print(f"[DEBUG RetrieveText] retrieveList: {self.retrieveList[:10] if self.retrieveList else 'EMPTY!'}")
        
        if not self.retrieveList:
            print("[ERROR] retrieveList is EMPTY! No documents to retrieve from!")
            return

        # Step1 : Get evidence segments
        evidence_segments = self.sampler.get_evidence_segments()
        print(f"[DEBUG RetrieveText] Got evidence segments for {len(evidence_segments)} attributes")
        print(f"[DEBUG RetrieveText] Evidence segments keys: {list(evidence_segments.keys())}")
        print(f"[DEBUG RetrieveText] Evidence segments counts: {[(col, len(segs)) for col, segs in evidence_segments.items()]}")(f"[DEBUG RetrieveText] Evidence segments keys: {list(evidence_segments.keys())}")
        
        # Step 2: For each attribute, use evidence-augmented retrieval
        # According to QUEST paper Section 4.2:
        # 1. Embed evidence segments
        # 2. Cluster embeddings using k-means (k=3)
        # 3. Use cluster centers to query for relevant chunks
        # 4. Merge and deduplicate results
        
        for doc_id in self.retrieveList:
            nowDict = {}
            for column in columns:
                retrieved_chunks = self._retrieve_with_evidence(
                    doc_id, 
                    column, 
                    evidence_segments.get(column, []),
                    topk=settings.TOPK
                )
                nowDict[column] = retrieved_chunks
                print(f"[DEBUG RetrieveText] doc_id={doc_id}, column={column}: retrieved {len(retrieved_chunks)} chunks, total length={sum(len(str(c)) for c in retrieved_chunks)}")
            self.output.append(TextDictPack(doc_id, nowDict))
        
        print(f"[DEBUG RetrieveText] Created {len(self.output)} TextDictPack objects")
        if self.output:
            print(f"[DEBUG RetrieveText] Sample output - doc_id: {self.output[0].doc_id}, columns: {list(self.output[0].textDict.keys())}")
    
    def _retrieve_with_evidence(self, doc_id, column, evidence_segments, topk=5):
        """
        Evidence-augmented retrieval for a single attribute.
        
        According to QUEST paper Section 4.2:
        - If evidence segments exist: embed them, cluster with k-means (k=3),
          use cluster centers as queries
        - If no evidence: use attribute description
        - Merge results from all queries and deduplicate
        """
        if not evidence_segments or len(evidence_segments) == 0:
            # Fallback: use attribute name + description as query
            attr_schema_evidence = self.sampler.get_attr_schema_evidence()
            query_text = attr_schema_evidence.get(column, column)
            chunks = self.indexer.get_relative_chunks_text_with_id(doc_id, query_text, topk=topk)
            print(f"[DEBUG _retrieve_with_evidence] NO EVIDENCE for '{column}', used description: {query_text[:80] if len(str(query_text)) > 80 else query_text}")
            print(f"[DEBUG _retrieve_with_evidence]   doc_id={doc_id}, column={column}: Got {len(chunks)} chunks, lengths={[len(str(c))[:20] for c in chunks[:3]]}")
            return chunks
        
        # Step 1: Embed evidence segments
        print(f"[DEBUG _retrieve_with_evidence] Embedding {len(evidence_segments)} evidence segments for '{column}'")
        # Use indexer's embedding model to batch embed all evidence segments
        evidence_embeddings = self.indexer.embedding_model.embed_documents(evidence_segments)
        
        evidence_embeddings = np.array(evidence_embeddings, dtype=np.float32)
        
        # Step 2: Cluster embeddings using k-means (k=3 or less if fewer segments)
        k = min(settings.N_CLUSTERS, len(evidence_segments))
        if k == 1:
            # Only one segment, use it directly
            cluster_centers = evidence_embeddings
        else:
            print(f"[DEBUG _retrieve_with_evidence] Clustering into k={k} clusters")
            cluster_centers, _ = faiss_kmeans_clustering(evidence_embeddings, n_clusters=k)
        
        # Step 3: Query using each cluster center
        all_chunks = []
        seen_chunk_ids = set()
        
        for i, center_emb in enumerate(cluster_centers):
            # Query storage directly with embedding
            results = self.indexer.storage.query_chunk_with_id(
                doc_id=doc_id,
                topk=topk,
                query_embedding=center_emb
            )
            
            # Deduplicate based on chunk_id
            for chunk_text, similarity, ret_doc_id, chunk_id in results:
                if chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk_id)
                    all_chunks.append((chunk_text, chunk_id))
        
        print(f"[DEBUG _retrieve_with_evidence] Retrieved {len(all_chunks)} unique chunks for '{column}' (from {k} queries)")
        return all_chunks



        

