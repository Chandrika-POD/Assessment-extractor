"""Archive source bytes and collect portable images without executing source markup."""
import base64
import hashlib

MAX_IMAGES = 100
MAX_IMAGE_BYTES = 40 * 1024 * 1024
MAX_DOCUMENTS = 100


def archive(body, mime, url):
    return {'url': url, 'mime_type': mime.split(';')[0].strip(), 'byte_count': len(body),
            'sha256': hashlib.sha256(body).hexdigest(),
            'encoding': 'base64', 'data_base64': base64.b64encode(body).decode('ascii')}


def raster_type(body):
    if body.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if body.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if body.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if body.startswith(b'RIFF') and body[8:12] == b'WEBP':
        return 'image/webp'
    return None


def collect_images(images, fetch):
    total = 0
    for index, image in enumerate(images):
        if index >= MAX_IMAGES or total >= MAX_IMAGE_BYTES:
            image.update(status='limit_reached', error='Image collection budget reached; source URL retained.')
            continue
        try:
            final, mime, body = fetch(image['url'])
            if total + len(body) > MAX_IMAGE_BYTES:
                image.update(status='limit_reached', error='Image collection byte budget reached.')
                continue
            kind = raster_type(body)
            # SVG and other active formats are never embedded into the exported document.
            if not kind:
                image.update(status='unsupported_format', error='Only PNG, JPEG, GIF and WebP can be embedded safely.')
                continue
            image.update(status='saved', resolved_url=final, archive=archive(body, kind, final))
            total += len(body)
        except (OSError, ValueError) as exc:
            image.update(status=getattr(exc, 'status', 'failed'), error=str(exc))


def coverage(result):
    images = result.get('images', [])
    docs = result.get('documents', [])
    tabs = result.get('browser', {}).get('tabs', [])
    return {'status': 'needs_source_review', 'complete_capture_verified': False,
        'tables_saved': len(result.get('tables', [])),
        'images_discovered': len(images), 'images_saved': sum(i['status'] == 'saved' for i in images),
        'documents_discovered': len(docs), 'documents_archived': sum(bool(d.get('archive')) for d in docs),
        'document_texts_extracted': sum(d['status'] == 'processed' for d in docs),
        'tabs_captured': sum(t['status'] == 'captured' for t in tabs),
        'unresolved': ([{'kind': 'image', 'url': i['url'], 'status': i['status'], 'error': i.get('error')}
                        for i in images if i['status'] != 'saved'] +
                       [{'kind': 'document', 'url': d['url'], 'status': d['status'], 'error': d.get('error')}
                        for d in docs if d['status'] not in ('processed', 'retained_excerpt')] +
                       [{'kind': 'tab', **t} for t in tabs if t['status'] != 'captured'] +
                       result.get('embedded_media', []) + result.get('browser', {}).get('capture_gaps', []) +
                       ([{'kind': 'browser', 'status': 'failed', 'error': result['browser'].get('error')}]
                        if result.get('browser', {}).get('status') == 'failed' else [])),
        'scope': 'Submitted assessment page, captured tabs, discovered images and directly linked PDFs. Other linked webpages are listed, not recursively crawled.',
        'limits': {'max_images': MAX_IMAGES, 'image_bytes': MAX_IMAGE_BYTES, 'max_documents': MAX_DOCUMENTS,
                   'individual_download_bytes': 3 * 1024 * 1024},
        'notes': ['Original PDFs preserve their visual layout; PDF text alone does not preserve diagrams or scanned text.',
                  'OCR, embedded videos, interactive canvas and inline SVG rendering are not implemented.',
                  'Source HTML is archived as data, never executed in the generated document.']}
