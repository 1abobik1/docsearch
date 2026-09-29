class DomainError(Exception):
    """Base class for errors that are part of the service contract."""


class DocumentNotFoundError(DomainError):
    def __init__(self, document_id: int) -> None:
        super().__init__(f"Document {document_id} not found")
        self.document_id = document_id


class SearchUnavailableError(DomainError):
    """The search backend could not serve the request."""
