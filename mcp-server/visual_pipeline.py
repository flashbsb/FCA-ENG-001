"""Extração e inventário rastreável de imagens para revisão visual assistida."""
from __future__ import annotations

import hashlib
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


MAX_ASSETS_PER_LOT = 64
MAX_ASSET_BYTES = 12 * 1024 * 1024
MAX_RENDERED_PAGES_PER_PDF = 48
PAGE_VISUAL_HINTS = re.compile(
    r"\b(?:figura\s+\d+|figure\s+\d+|diagrama|diagram|topologia|topology|"
    r"arquitetura\s+(?:da\s+)?(?:solu[cç][aã]o|rede)|network\s+topology|"
    r"desenho\s+(?:da\s+)?solu[cç][aã]o|vis[aã]o\s+geral\s+da\s+arquitetura)\b",
    re.I,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _image_extension(data: bytes, proposed: str = "") -> str:
    ext = Path(proposed).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".jp2", ".svg", ".drawio"}:
        return ".jpg" if ext == ".jpeg" else ext
    try:
        from PIL import Image
        from io import BytesIO
        fmt = (Image.open(BytesIO(data)).format or "").lower()
        return {"jpeg": ".jpg", "png": ".png", "bmp": ".bmp", "gif": ".gif",
                "webp": ".webp", "tiff": ".tiff", "jpeg2000": ".jp2"}.get(fmt, ".bin")
    except Exception:
        return ".bin"


def _dimensions(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(data)) as image:
            return image.width, image.height
    except Exception:
        return None, None


def _vector_labels(data: bytes, extension: str) -> str:
    """Extrai rótulos e arestas declarados em SVG/DrawIO sem afirmar análise visual."""
    try:
        root = ET.fromstring(data)
    except Exception:
        return ""
    labels = []
    edges = []
    id_to_label = {}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        attrs = {key.rsplit("}", 1)[-1].lower(): value for key, value in element.attrib.items()}
        if extension == ".svg":
            if tag in ("text", "title", "desc"):
                value = " ".join(part.strip() for part in element.itertext() if part.strip())
                if value:
                    labels.append(value)
            for key in ("aria-label", "title", "alt"):
                if attrs.get(key):
                    labels.append(attrs[key])
        elif extension == ".drawio":
            value = attrs.get("value", "").strip()
            if value and attrs.get("vertex") == "1":
                id_to_label[attrs.get("id", "")] = value
                labels.append(value)
            if attrs.get("edge") == "1":
                edges.append((attrs.get("source", ""), attrs.get("target", "")))
    unique_labels = list(dict.fromkeys(re.sub(r"<[^>]+>", " ", value).strip() for value in labels if value.strip()))
    lines = ["Rótulos vetoriais: " + "; ".join(unique_labels[:500])] if unique_labels else []
    resolved_edges = [f"{id_to_label.get(source, source)} -> {id_to_label.get(target, target)}" for source, target in edges]
    if resolved_edges:
        lines.append("Conexões declaradas no DrawIO: " + "; ".join(resolved_edges[:500]))
    return "\n".join(lines)


def _ocr_text(asset_path: str, tesseract: str | None, languages: str) -> tuple[str, str]:
    if not tesseract:
        return "", "indisponível: tesseract não instalado/configurado"
    try:
        result = subprocess.run(
            [tesseract, asset_path, "stdout", "-l", languages],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout[:12000].strip(), "concluído"
        return "", "falhou: " + (result.stderr.strip()[:300] or f"código {result.returncode}")
    except subprocess.TimeoutExpired:
        return "", "interrompido: limite de 20 segundos excedido"
    except Exception as exc:
        return "", "falhou: " + str(exc)[:300]


def _save_asset(data: bytes, *, source: str, kind: str, output_dir: str,
                page: int | None = None, member: str | None = None,
                proposed_name: str = "", tesseract: str | None = None,
                languages: str = "eng") -> dict | None:
    if not data or len(data) > MAX_ASSET_BYTES:
        return None
    content_hash = _sha256(data)
    location_key = f"{source}|{kind}|{page or ''}|{member or ''}|{content_hash}"
    asset_id = "IMG-" + hashlib.sha256(location_key.encode("utf-8")).hexdigest()[:12].upper()
    extension = _image_extension(data, proposed_name)
    filename = asset_id + extension
    os.makedirs(output_dir, exist_ok=True)
    full_path = os.path.join(output_dir, filename)
    with open(full_path, "wb") as stream:
        stream.write(data)
    width, height = _dimensions(data)
    if extension in (".svg", ".drawio"):
        ocr = _vector_labels(data, extension)
        ocr_status = "rótulos e conexões vetoriais extraídos" if ocr else "arquivo vetorial preservado; sem rótulos XML recuperáveis"
    else:
        ocr, ocr_status = _ocr_text(full_path, tesseract, languages)
    return {
        "asset_id": asset_id, "source_document": source, "kind": kind,
        "page": page, "package_member": member,
        "file": "visuais/" + filename, "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
        "sha256": content_hash, "size_bytes": len(data), "width": width, "height": height,
        "ocr_status": ocr_status, "ocr_text": ocr,
    }


def _extract_docx_images(path: str, relative_path: str, output_dir: str,
                         tesseract: str | None, languages: str, remaining: int) -> list[dict]:
    assets = []
    try:
        with zipfile.ZipFile(path) as archive:
            members = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
            for member in members[:remaining]:
                try:
                    row = _save_asset(archive.read(member), source=relative_path,
                                      kind="imagem_embutida_docx", output_dir=output_dir,
                                      member=member, proposed_name=member,
                                      tesseract=tesseract, languages=languages)
                    if row:
                        assets.append(row)
                except Exception:
                    continue
    except Exception:
        pass
    return assets


def _render_pdf_page(path: str, page_number: int, output_dir: str, relative_path: str,
                     tesseract: str | None, languages: str) -> dict | None:
    executable = os.environ.get("FCA_PDFTOPPM") or shutil.which("pdftoppm")
    if not executable:
        return None
    os.makedirs(output_dir, exist_ok=True)
    stem = "render_" + hashlib.sha256(f"{relative_path}|{page_number}".encode("utf-8")).hexdigest()[:12]
    prefix = os.path.join(output_dir, stem)
    try:
        result = subprocess.run(
            [executable, "-f", str(page_number), "-l", str(page_number), "-singlefile",
             "-png", "-r", "140", path, prefix],
            capture_output=True, text=True, timeout=35, check=False,
        )
        rendered_path = prefix + ".png"
        if result.returncode != 0 or not os.path.isfile(rendered_path):
            return None
        with open(rendered_path, "rb") as stream:
            data = stream.read(MAX_ASSET_BYTES + 1)
        os.remove(rendered_path)
        return _save_asset(data, source=relative_path, kind="pagina_pdf_renderizada",
                           output_dir=output_dir, page=page_number, proposed_name="pagina.png",
                           tesseract=tesseract, languages=languages)
    except Exception:
        return None


def _extract_pdf_images(path: str, relative_path: str, output_dir: str,
                        tesseract: str | None, languages: str, remaining: int) -> tuple[list[dict], int, str, dict]:
    assets: list[dict] = []
    rendered_pages = 0
    candidate_pages: list[int] = []
    unrendered_pages: list[int] = []
    status = "extração pypdf"
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        candidate_pages = []
        embedded_budget = max(1, remaining - min(MAX_RENDERED_PAGES_PER_PDF, remaining // 3))
        for page_number, page in enumerate(reader.pages, 1):
            try:
                for image in page.images:
                    if len(assets) >= embedded_budget:
                        break
                    image_data = image.data
                    if len(image_data) < 1024:
                        continue
                    width, height = _dimensions(image_data)
                    if width is not None and height is not None and (width < 160 or height < 100):
                        continue
                    row = _save_asset(image_data, source=relative_path,
                                      kind="imagem_embutida_pdf", output_dir=output_dir,
                                      page=page_number, proposed_name=image.name,
                                      tesseract=tesseract, languages=languages)
                    if row:
                        assets.append(row)
            except Exception:
                pass
            page_text = page.extract_text() or ""
            if re.search(r"\b(?:table of contents|sum[aá]rio|lista de figuras|listas de figuras|table of figures)\b", page_text, re.I):
                continue
            if PAGE_VISUAL_HINTS.search(page_text):
                candidate_pages.append(page_number)
        render_candidates = candidate_pages[:MAX_RENDERED_PAGES_PER_PDF]
        unrendered_pages.extend(candidate_pages[MAX_RENDERED_PAGES_PER_PDF:])
        for index, page_number in enumerate(render_candidates):
            if len(assets) >= remaining:
                unrendered_pages.extend(render_candidates[index:])
                break
            row = _render_pdf_page(path, page_number, output_dir, relative_path, tesseract, languages)
            if row:
                assets.append(row)
                rendered_pages += 1
            else:
                unrendered_pages.append(page_number)
        status = f"extração pypdf; {len(reader.pages)} páginas"
    except Exception as exc:
        status = "falhou: " + str(exc)[:300]
    coverage = {
        "visual_hint_pages": candidate_pages,
        "unrendered_visual_pages": sorted(set(unrendered_pages)),
    }
    return assets, rendered_pages, status, coverage


def extract_visual_inventory(source_root: str, output_dir: str,
                             documents: list[dict], max_assets: int = MAX_ASSETS_PER_LOT) -> dict:
    """Extrai mídias raster/embutidas e renderiza páginas de PDF com sinais visuais."""
    assets: list[dict] = []
    details: list[dict] = []
    tesseract = os.environ.get("FCA_TESSERACT") or shutil.which("tesseract")
    languages = os.environ.get("FCA_TESSERACT_LANG", "por+eng")
    if tesseract:
        try:
            langs = subprocess.run([tesseract, "--list-langs"], capture_output=True,
                                   text=True, timeout=10, check=False).stdout
            if "por" not in langs and "eng" in langs:
                languages = "eng"
            elif "por" in langs and "eng" not in langs:
                languages = "por"
        except Exception:
            languages = "eng"

    os.makedirs(output_dir, exist_ok=True)
    image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".svg", ".drawio"}
    for doc in documents:
        if len(assets) >= max_assets:
            break
        relative_path = doc.get("relative_path", "")
        source_path = os.path.abspath(os.path.join(source_root, relative_path))
        ext = os.path.splitext(relative_path)[1].lower()
        before = len(assets)
        rendered = 0
        status = ""
        coverage = {"visual_hint_pages": [], "unrendered_visual_pages": []}
        try:
            if ext in image_extensions:
                with open(source_path, "rb") as stream:
                    data = stream.read(MAX_ASSET_BYTES + 1)
                row = _save_asset(data, source=relative_path, kind="imagem_solteira",
                                  output_dir=output_dir, proposed_name=relative_path,
                                  tesseract=tesseract, languages=languages)
                if row:
                    assets.append(row)
                status = "arquivo visual incluído no inventário"
            elif ext == ".docx":
                rows = _extract_docx_images(source_path, relative_path, output_dir,
                                            tesseract, languages, max_assets - len(assets))
                assets.extend(rows)
                status = "mídias word/media extraídas"
            elif ext == ".pdf":
                rows, rendered, status, coverage = _extract_pdf_images(
                    source_path, relative_path, output_dir, tesseract, languages,
                    max_assets - len(assets))
                assets.extend(rows)
            else:
                continue
        except Exception as exc:
            status = "falhou: " + str(exc)[:300]
        details.append({"source_document": relative_path, "status": status,
                        "assets_added": len(assets) - before, "rendered_pages": rendered,
                        **coverage})

    for index, asset in enumerate(assets, 1):
        asset["sequence"] = index
    pages_not_rendered = [
        {"source_document": item["source_document"], "pages": item["unrendered_visual_pages"]}
        for item in details if item.get("unrendered_visual_pages")
    ]
    limitations = []
    if not tesseract and assets:
        limitations.append("OCR indisponível; imagens podem ser entregues ao modelo multimodal pelo MCP.")
    if pages_not_rendered:
        limitations.append("Há páginas com indícios visuais que não foram renderizadas; ver unrendered_visual_pages por documento.")
    inventory = {
        "schema_version": "1.0",
        "asset_count": len(assets),
        "rendered_pdf_pages": sum(item["rendered_pages"] for item in details),
        "ocr_available": bool(tesseract),
        "ocr_engine": os.path.basename(tesseract) if tesseract else None,
        "visual_analysis_status": "aguardando interpretação visual" if assets else "sem imagens extraídas",
        "limits": {"max_assets_per_lot": max_assets, "max_asset_bytes": MAX_ASSET_BYTES,
                   "max_rendered_pages_per_pdf": MAX_RENDERED_PAGES_PER_PDF},
        "assets_may_be_truncated": len(assets) >= max_assets or bool(pages_not_rendered),
        "unrendered_visual_pages": pages_not_rendered,
        "limitations": limitations,
        "sources": details,
        "assets": assets,
    }
    inventory_path = os.path.join(os.path.dirname(output_dir), "inventario_visual.json")
    with open(inventory_path, "w", encoding="utf-8") as stream:
        json.dump(inventory, stream, ensure_ascii=False, indent=2)
    return inventory


def make_mcp_image(path: str) -> tuple[str, str]:
    """Prepara imagem visual para um bloco de conteúdo MCP, redimensionando com Pillow se disponível."""
    with open(path, "rb") as stream:
        raw = stream.read(MAX_ASSET_BYTES + 1)
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(raw)) as image:
            image.thumbnail((1600, 1600))
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            out = BytesIO()
            image.save(out, format="PNG", optimize=True)
            return base64.b64encode(out.getvalue()).decode("ascii"), "image/png"
    except Exception:
        mime = mimetypes.guess_type(path)[0]
        if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"):
            raise ValueError(f"Formato de imagem não suportado para exibição: {path}")
        return base64.b64encode(raw).decode("ascii"), mime
