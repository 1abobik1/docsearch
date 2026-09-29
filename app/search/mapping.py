from typing import Any

# Texts are mostly Russian with some English words and emoji. Russian and English
# stemmers touch disjoint alphabets, so chaining them is safe; "ё" is folded to "е"
# because people type both interchangeably.
INDEX_SETTINGS: dict[str, Any] = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
        "char_filter": {
            "yo_to_e": {"type": "mapping", "mappings": ["ё => е", "Ё => Е"]},
        },
        "filter": {
            "russian_stop": {"type": "stop", "stopwords": "_russian_"},
            "russian_stemmer": {"type": "stemmer", "language": "russian"},
            "english_stop": {"type": "stop", "stopwords": "_english_"},
            "english_stemmer": {"type": "stemmer", "language": "english"},
        },
        "analyzer": {
            "text_ru_en": {
                "type": "custom",
                "char_filter": ["yo_to_e"],
                "tokenizer": "standard",
                "filter": [
                    "lowercase",
                    "russian_stop",
                    "english_stop",
                    "russian_stemmer",
                    "english_stemmer",
                ],
            },
        },
    },
}

# The index mirrors exactly the fields required by the spec: `id` and `text`.
INDEX_MAPPINGS: dict[str, Any] = {
    "dynamic": "strict",
    "properties": {
        "id": {"type": "long"},
        "text": {"type": "text", "analyzer": "text_ru_en"},
    },
}
