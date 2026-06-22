# Author: Junjun
# Date: 2025/9/23
import numpy as np


def cosine_similarity(vec_a, vec_b):
    """计算两个向量的余弦相似度（numpy 加速版）"""
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def batch_cosine_similarity(query_vec, doc_vecs):
    """批量计算一个 query 向量与多个 doc 向量的余弦相似度

    Args:
        query_vec: 查询向量 (1D)
        doc_vecs: 文档向量列表 (2D: N x dim)

    Returns:
        list[float]: 每个文档与查询的相似度分数
    """
    if not doc_vecs:
        return []

    q = np.asarray(query_vec, dtype=np.float32)
    docs = np.asarray(doc_vecs, dtype=np.float32)

    if docs.ndim == 1:
        docs = docs.reshape(1, -1)

    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return [0.0] * len(docs)

    dot_products = docs @ q
    doc_norms = np.linalg.norm(docs, axis=1)

    # 避免除零
    denominators = doc_norms * q_norm
    denominators[denominators == 0] = 1.0

    similarities = dot_products / denominators
    return similarities.tolist()
