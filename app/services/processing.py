import io
import logging
import uuid

import httpx
from pypdf import PdfReader
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.document_content import DocumentContent
from app.models.file import File
from app.services import chunking, storage
from app.services.ollama import embed

logger = logging.getLogger(__name__)


async def process_pdf(file_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(File).where(File.id == file_id))
            db_file = result.scalar_one_or_none()
            if db_file is None:
                return

            db_file.processing_status = "processing"
            await db.commit()

            # Download PDF from GCS
            signed_url = await storage.generate_signed_url(db_file.gcs_path)
            async with httpx.AsyncClient() as client:
                resp = await client.get(signed_url, timeout=60)
                resp.raise_for_status()
                pdf_bytes = resp.content

            # Extract text page-by-page
            reader = PdfReader(io.BytesIO(pdf_bytes))
            total_pages = len(reader.pages)
            await db.refresh(db_file)
            db_file.pages_total = total_pages
            await db.commit()

            # Process each page
            for page_index, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                chunks = chunking.chunk_text(
                    page_text,
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                )

                if not chunks:
                    await db.refresh(db_file)
                    db_file.pages_processed = page_index + 1
                    await db.commit()
                    continue

                # Batch embed all chunks for this page
                embeddings = await embed(chunks)

                # Determine page label (e.g. "i", "ii", "1", "2", etc.)
                try:
                    page_label = reader.page_labels[page_index]
                except Exception:
                    page_label = str(page_index + 1)

                # Insert DocumentContent rows
                for chunk_index, (chunk_text, vector) in enumerate(zip(chunks, embeddings)):
                    db.add(DocumentContent(
                        file_id=file_id,
                        page_number=page_index + 1,
                        page_label=page_label,
                        chunk_index=chunk_index,
                        is_learning_material=True,
                        content=chunk_text,
                        content_vector=vector,
                    ))

                await db.refresh(db_file)
                db_file.pages_processed = page_index + 1
                await db.commit()

            # Done
            await db.refresh(db_file)
            db_file.processing_status = "completed"
            await db.commit()

        except Exception:
            logger.exception("Failed to process PDF file_id=%s", file_id)
            try:
                await db.refresh(db_file)
                db_file.processing_status = "failed"
                await db.commit()
            except Exception:
                logger.exception("Failed to update status for file_id=%s", file_id)