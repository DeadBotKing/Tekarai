"""Isolated, bounded text extraction worker; not a web endpoint. No OCR or tools."""
import io
import json
import sys
import zipfile
import xml.etree.ElementTree as ET

LIMIT = 4 * 1024 * 1024

def extract(data, suffix):
    if suffix in {'.txt', '.md', '.csv'}:
        encoding = 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
        return [{'page': None, 'text': data.decode(encoding, errors='strict')[:32000]}]
    if suffix == '.docx':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 20 * 1024 * 1024:
                raise ValueError('Archive too large')
            with archive.open('word/document.xml') as stream:
                xml = stream.read(2 * 1024 * 1024 + 1)
            if len(xml) > 2 * 1024 * 1024 or b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
                raise ValueError('Unsafe XML')
            root = ET.fromstring(xml)
            return [{'page': None, 'text': '\n'.join(node.text or '' for node in root.iter() if node.tag.endswith('}t'))[:32000]}]
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF')
        segments = []
        remaining = 32000
        for i, page in enumerate(reader.pages):
            if i >= 15 or remaining <= 0:
                break
            text = (page.extract_text() or '')[:remaining]
            remaining -= len(text)
            segments.append({'page': i + 1, 'text': text})
        return segments
    raise ValueError('Unsupported format')

if __name__ == '__main__':
    try:
        if sys.platform != 'win32':
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        if len(sys.argv) == 3 and sys.argv[1] == '.pdf':
            from pathlib import Path
            packages = Path(sys.argv[2]).resolve()
            if not (packages / 'pypdf' / '__init__.py').is_file():
                raise ValueError('Parser package unavailable')
            sys.path.insert(0, str(packages))
        raw = sys.stdin.buffer.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('File too large')
        result = extract(raw, sys.argv[1])
        print(json.dumps({'segments': result}, ensure_ascii=False))
    except Exception:
        # No raw exception/file contents on stderr or in the API response.
        print(json.dumps({'segments': [], 'unreadable': True}))
        sys.exit(1)
