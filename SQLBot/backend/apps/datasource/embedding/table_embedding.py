# Author: Junjun
# Date: 2025/9/23
import json
import time
import traceback

from apps.ai_model.embedding import EmbeddingModelCache
from apps.datasource.embedding.utils import cosine_similarity, batch_cosine_similarity
from common.core.config import settings
from common.utils.utils import SQLBotLogUtil

# 最低相似度阈值，低于此值的结果将被过滤
MIN_SIMILARITY_THRESHOLD = 0.3


def get_table_embedding(tables: list[dict], question: str):
    _list = []
    for table in tables:
        _list.append({"id": table.get('id'), "schema_table": table.get('schema_table'), "cosine_similarity": 0.0})

    if _list:
        try:
            text = [s.get('schema_table') for s in _list]

            model = EmbeddingModelCache.get_model()
            start_time = time.time()
            results = model.embed_documents(text)
            end_time = time.time()
            SQLBotLogUtil.info(f"Embedding documents took {end_time - start_time:.3f}s")

            q_embedding = model.embed_query(question)

            # 批量计算余弦相似度（numpy 加速）
            similarities = batch_cosine_similarity(q_embedding, results)
            for i, sim in enumerate(similarities):
                _list[i]['cosine_similarity'] = sim

            _list.sort(key=lambda x: x['cosine_similarity'], reverse=True)

            # 相似度阈值过滤
            _list = [item for item in _list if item['cosine_similarity'] >= MIN_SIMILARITY_THRESHOLD]

            _list = _list[:settings.TABLE_EMBEDDING_COUNT]
            SQLBotLogUtil.info(json.dumps(_list))
            return _list
        except Exception:
            traceback.print_exc()
    return _list


def calc_table_embedding(tables: list[dict], question: str):
    _list = []
    for table in tables:
        _list.append(
            {"id": table.get('id'), "schema_table": table.get('schema_table'), "embedding": table.get('embedding'),
             "cosine_similarity": 0.0, "table_name": table.get('table_name')})

    if _list:
        try:
            model = EmbeddingModelCache.get_model()
            start_time = time.time()

            q_embedding = model.embed_query(question)

            # 解析预存储的 embedding 并批量计算
            valid_indices = []
            doc_vecs = []
            for i, item in enumerate(_list):
                emb = item.get('embedding')
                if emb:
                    parsed = json.loads(emb) if isinstance(emb, str) else emb
                    doc_vecs.append(parsed)
                    valid_indices.append(i)

            if doc_vecs:
                similarities = batch_cosine_similarity(q_embedding, doc_vecs)
                for idx, sim in zip(valid_indices, similarities):
                    _list[idx]['cosine_similarity'] = sim

            _list.sort(key=lambda x: x['cosine_similarity'], reverse=True)

            # 相似度阈值过滤
            _list = [item for item in _list if item['cosine_similarity'] >= MIN_SIMILARITY_THRESHOLD]

            _list = _list[:settings.TABLE_EMBEDDING_COUNT]
            end_time = time.time()
            SQLBotLogUtil.info(f"Table embedding calc took {end_time - start_time:.3f}s")
            SQLBotLogUtil.info(json.dumps([{"id": ele.get('id'), "schema_table": ele.get('schema_table'),
                                            "cosine_similarity": ele.get('cosine_similarity'),
                                            "table_name": ele.get('table_name')}
                                           for ele in _list]))
            return _list
        except Exception:
            traceback.print_exc()
    return _list
