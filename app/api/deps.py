from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.repositories.documents import SqlUnitOfWork
from app.search.index import ElasticsearchDocumentIndex
from app.services.documents import DocumentService


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


def get_es_client(request: Request) -> AsyncElasticsearch:
    client: AsyncElasticsearch = request.app.state.es
    return client


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
EsClientDep = Annotated[AsyncElasticsearch, Depends(get_es_client)]


def get_document_service(
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
    es: EsClientDep,
) -> DocumentService:
    return DocumentService(
        uow_factory=lambda: SqlUnitOfWork(session_factory),
        index=ElasticsearchDocumentIndex(es, settings.elasticsearch_index),
        search_limit=settings.search_limit,
    )


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
