"""Provider-independent source parsing. Extracted items always require review."""
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

RESPONSE_LABELS = sorted([
    'More than half the days', 'Nearly every day', 'Several days', 'Not at all', 'A little bit',
    'Quite a bit', 'Moderately', 'Extremely', 'Very often', 'Almost always', 'Almost never',
    'Strongly disagree', 'Strongly agree', 'Somewhat disagree', 'Somewhat agree',
    'Never', 'Rarely', 'Sometimes', 'Often', 'Always', 'Disagree', 'Agree', 'Neutral', 'Yes', 'No',
], key=len, reverse=True)
LABEL_PATTERN = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(label) for label in RESPONSE_LABELS) + r')(?!\w)', re.I)


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self, tags=None):
        if tags is None or self.tag in tags:
            yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk(tags)

    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(c.text() if isinstance(c, Node) else c for c in self.children)).strip()


class Tree(HTMLParser):
    VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def visible(node):
    if (node.tag in {'script', 'style', 'nav', 'footer', 'noscript', 'svg', 'template', 'head'}
        or 'hidden' in node.attrs or node.attrs.get('aria-hidden') == 'true'
        or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', node.attrs.get('style', ''), re.I)):
        return False
    node.children = [c for c in node.children if not isinstance(c, Node) or visible(c)]
    return True


def scope_for(root, url):
    """Only content-container selection is provider-specific."""
    host = urlsplit(url).hostname
    if host in {'novopsych.com', 'www.novopsych.com'}:
        entries = [n for n in root.walk() if 'entry-content' in n.attrs.get('class', '').split()]
        if not entries:
            entries = [n for n in root.walk() if n.attrs.get('data-elementor-type') in {'wp-post', 'single-post'}]
        if entries:
            return max(entries, key=lambda n: len(n.text())), 'novopsych'
    main = [n for n in root.walk() if (n.tag in {'main', 'article'} or n.attrs.get('role') == 'main') and len(n.text()) >= 40]
    if not main:
        main = [n for n in root.walk() if n.tag in {'div', 'section'} and len(n.text()) >= 40
                and re.fullmatch(r'(?:main|inner)?[-_]?content(?:[-_]?(?:area|wrapper))?', n.attrs.get('id', ''), re.I)]
        # Prefer the inner article container over wrappers that include site navigation.
        inner = [n for n in main if 'inner' in n.attrs.get('id', '').lower()]
        if inner:
            main = inner
    return max(main, key=lambda n: len(n.text()), default=root), 'generic'


def parse_html(html, url):
    tree = Tree()
    tree.feed(html)
    root = tree.root
    page_title = next((n.text() for n in root.walk({'title'})), None)
    description = next((n.attrs.get('content') for n in root.walk({'meta'}) if n.attrs.get('name', '').lower() == 'description'), None)
    visible(root)
    scope, provider = scope_for(root, url)
    headings = list(scope.walk({'h1', 'h2'}))
    name = next((n.text() for n in headings if n.tag == 'h1'), None) or next((n.text() for n in headings), page_title)
    result = {'name': name, 'description': description, 'provider': provider, 'sections': [], 'tables': [], 'links': [], 'list_items': []}
    current = {'title': 'Overview', 'text': '', 'source_url': url}
    def visit(node, ordinal=None):
        nonlocal current
        if re.fullmatch('h[1-6]', node.tag):
            if current['text'].strip():
                result['sections'].append(current)
            current = {'title': node.text(), 'text': '', 'source_url': url}
        elif node.tag == 'table':
            rows = [[c.text() for c in row.children if isinstance(c, Node) and c.tag in {'th', 'td'}] for row in node.walk({'tr'})]
            rows = [r for r in rows if r]
            result['tables'].append({'rows': rows, 'section': current['title'], 'source_url': url})
            current['text'] += '\n'.join(' | '.join(row) for row in rows) + '\n'
        elif node.tag == 'ol':
            ordinal = 0
            for child in node.children:
                if isinstance(child, Node):
                    if child.tag == 'li':
                        ordinal += 1
                    visit(child, ordinal if child.tag == 'li' else None)
        elif node.tag in {'p', 'li', 'blockquote'}:
            text = node.text()
            current['text'] += (f'{ordinal}. ' if ordinal else '') + text + '\n'
            if ordinal:
                result['list_items'].append({'number': ordinal, 'text': text, 'section': current['title'], 'source_url': url})
        else:
            for child in node.children:
                if isinstance(child, Node):
                    visit(child)
                elif child.strip():
                    current['text'] += re.sub(r'\s+', ' ', child).strip() + '\n'
    visit(scope)
    if current['text'].strip():
        result['sections'].append(current)
    for node in scope.walk({'a'}):
        href = node.attrs.get('href', '')
        if not href or href.startswith('#'):
            continue
        try:
            target = urljoin(url, href)
            if urlsplit(target).scheme == 'https':
                result['links'].append({'url': target, 'title': node.text() or urlsplit(target).path.rsplit('/', 1)[-1]})
        except ValueError:
            continue
    result['links'] = list({v['url']: v for v in result['links']}.values())
    return result


def item(text, source, ordinal=None, options=None):
    return {'text': text, 'number': ordinal, 'type': 'unverified', 'reverse_scored': None,
            'review_status': 'needs_review', 'options': options or [], 'source': source}


def html_questions(parsed):
    items = []
    for index, table in enumerate(parsed['tables'], 1):
        rows = table['rows']
        if len(rows) < 2:
            continue
        header = rows[0]
        column = next((i for i, v in enumerate(header) if re.search(r'question|statement|symptom|^item(?: text)?$', v, re.I)), None)
        if column is None:
            continue
        # A leading "Item" column may contain item numbers rather than wording.
        if column == 0 and len(header) > 1 and re.fullmatch(r'\d+[.)]?', rows[1][0]):
            column = 1
        for row in rows[1:]:
            if len(row) != len(header) or len(row[column]) < 8:
                continue
            options = []
            for label, value in zip(header[column+1:], row[column+1:]):
                if label and re.fullmatch(r'-?\d+(?:\.\d+)?', value.strip()):
                    number = float(value) if '.' in value else int(value)
                    options.append({'label': label, 'response_value': number, 'score': None})
            items.append(item(row[column], {'url': table['source_url'], 'locator': f'Table {index}: {table["section"]}', 'source_row': row}, row[0] if column else None, options))
    for entry in parsed['list_items']:
        if re.search(r'questionnaire|questions|items', entry['section'], re.I):
            items.append(item(entry['text'], {'url': entry['source_url'], 'locator': entry['section']}, entry['number']))
    return items


def pdf_questions(text, url):
    """Read numbered rows and printed response columns, including per-item labels."""
    items = []
    numeric = re.compile(r'(?<!\S)-?\d+(?:\.\d+)?(?!\S)')
    tail_pattern = re.compile(r'(?:\s{2,}-?\d+(?:\.\d+)?){2,}\s*$')
    for page_number, page in enumerate(text.split('\f'), 1):
        lines = page.splitlines()
        starts = [(i, m) for i, line in enumerate(lines)
                  if (m := re.match(r'^ {0,8}(\d{1,3})(?:[.)]\s+|\s{2,}|\s*$)', line))]
        if len(starts) < 2:
            continue
        values = []
        for line in lines:
            tail = tail_pattern.search(line)
            if tail:
                values.append(list(numeric.finditer(line, tail.start())))
        runs = values[0] if values else []
        response_start = runs[0].start() if runs else None
        boundaries = []
        if len(runs) >= 2:
            centers = [(r.start()+r.end())/2 for r in runs]
            boundaries = [max(0, int(centers[0]-(centers[1]-centers[0])/2))]
            boundaries += [int((a+b)/2) for a,b in zip(centers, centers[1:])]
            boundaries += [max(len(l) for l in lines)+1]
        header_labels = []
        if response_start is not None:
            for line in reversed(lines[max(0, starts[0][0]-6):starts[0][0]]):
                cells = [c.strip() for c in re.split(r'\s{2,}', line[max(0,response_start-5):].strip()) if c.strip()]
                if len(cells) == len(runs) and all(re.search('[A-Za-z]', c) for c in cells):
                    header_labels = cells
                    break
                matches = [m.group() for m in LABEL_PATTERN.finditer(line[max(0,response_start-5):])]
                if len(matches) == len(runs):
                    header_labels = matches
                    break
        block_starts = []
        for line_index, _ in starts:
            begin = line_index
            # Vertically centered item numbers may follow the first line of wording.
            if not header_labels:
                while begin > 0 and lines[begin-1].strip() and line_index-begin < 3:
                    if any(i == begin-1 for i, _ in starts):
                        break
                    begin -= 1
            block_starts.append(begin)
        for pos, (line_index, match) in enumerate(starts):
            begin = block_starts[pos]
            stop = block_starts[pos+1] if pos+1 < len(starts) else len(lines)
            texts, numeric_row, blank = [], None, 0
            label_parts = [[] for _ in runs]
            if line_index > 0:
                previous = lines[line_index-1]
                tail = tail_pattern.search(previous)
                if tail and not previous[:tail.start()].strip():
                    numeric_row = list(numeric.finditer(previous, tail.start()))
            for j, line in enumerate(lines[begin:stop]):
                if re.search(r'Page\s+\d+\s+of|copyright|version date', line, re.I):
                    break
                if not line.strip():
                    blank += 1
                    if blank >= 2:
                        break
                    continue
                blank = 0
                tail = tail_pattern.search(line)
                if tail:
                    numeric_row = list(numeric.finditer(line, tail.start()))
                indent = len(line)-len(line.lstrip())
                if begin+j == line_index or not boundaries or indent < boundaries[0]:
                    if header_labels:
                        wording = line[:response_start]
                    else:
                        wording = line[:boundaries[0]] if boundaries else line
                    if begin+j == line_index:
                        wording = re.sub(r'^\s*\d{1,3}(?:[.)]\s+|\s{2,}|\s*$)', '', wording)
                    wording = wording.strip()
                    if wording:
                        texts.append(wording)
                if boundaries and not tail:
                    for k in range(len(runs)):
                        cell = line[boundaries[k]:boundaries[k+1]].strip()
                        if cell and re.search('[A-Za-z]', cell):
                            label_parts[k].append(cell)
            question = ' '.join(texts).strip()
            if len(question) < 8:
                continue
            row_labels = [' '.join(parts) for parts in label_parts]
            labels = header_labels or (row_labels if row_labels and all(row_labels) else [])
            options = []
            if labels and numeric_row and len(labels) == len(numeric_row):
                for label, run in zip(labels, numeric_row):
                    val = float(run.group()) if '.' in run.group() else int(run.group())
                    options.append({'label': label, 'response_value': val, 'score': None})
            items.append(item(question, {'url': url, 'page': page_number,
                'source_lines': [l.strip() for l in lines[begin:stop] if l.strip()]}, int(match.group(1)), options))
    return items


def map_sections(result):
    patterns = {'instructions': r'instruction|administration|completion', 'scoring': r'scor',
        'interpretation': r'interpret|cut.?off|severity', 'psychometrics': r'psychometric|reliability|validity',
        'normative_data': r'norm|percentile', 'references': r'reference|bibliograph|developer'}
    for field, pattern in patterns.items():
        matches = [s for s in result['sections'] if re.search(pattern, s['title'], re.I)]
        if matches:
            result[field] = matches
            result['field_provenance'][field] = [{'url': s['source_url'], 'locator': s['title']} for s in matches]
            if field in result['assessment']:
                result['assessment'][field] = matches
    if not result['assessment']['description']:
        section = next((s for s in result['sections'] if re.search(r'overview|description|about', s['title'], re.I)), None)
        if section:
            result['assessment']['description'] = section['text']
            result['field_provenance']['assessment.description'] = {'url': section['source_url'], 'locator': section['title']}
    if not result['instructions']:
        for section in result['sections']:
            match = re.search(r'(?im)^\s*Instructions?\s*:\s*(.+?)(?=\n\s*\n|\Z)', section['text'], re.S)
            if match:
                result['instructions'] = re.sub(r'\s+', ' ', match.group(1)).strip()
                result['field_provenance']['instructions'] = {'url': section['source_url'], 'locator': 'Explicit Instructions block'}
                break
            # PDF font spacing may split an Instructions heading into several words.
            lines = section['text'].splitlines()
            for index, line in enumerate(lines):
                if re.sub(r'\s|:', '', line).lower() not in {'instructions', 'instruction'}:
                    continue
                paragraph = []
                for following in lines[index+1:]:
                    if not following.strip():
                        if paragraph:
                            break
                        continue
                    paragraph.append(following.strip())
                if paragraph:
                    result['instructions'] = ' '.join(paragraph)
                    result['field_provenance']['instructions'] = {'url': section['source_url'], 'locator': 'Instructions heading in source text'}
                    break
            if result['instructions']:
                break
