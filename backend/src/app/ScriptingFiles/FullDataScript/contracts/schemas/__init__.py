"""Validated contract source documents and boundary types."""

from app.ScriptingFiles.FullDataScript.contracts.schemas.documents import (
    SourceDocument as SourceDocument,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.documents import (
    parse_source_document as parse_source_document,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.documents import (
    extract_tag_attribute,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.documents import (
    extract_tag_text,
)
from app.ScriptingFiles.FullDataScript.contracts.schemas.documents import (
    validate_page as validate_page,
)


tag_text = extract_tag_text


tag_attribute = extract_tag_attribute
