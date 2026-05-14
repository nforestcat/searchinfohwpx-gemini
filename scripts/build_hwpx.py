import json, zipfile, os, html, re, argparse, sys
from difflib import SequenceMatcher

def esc(t):
    return html.escape(str(t), quote=True)

def normalize_title(title):
    if not title: return ""
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t

def title_similarity(a, b):
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb: return 0.0
    return SequenceMatcher(None, na, nb).ratio()

def normalize_url(url):
    if not url: return ""
    u = url.strip().rstrip('/')
    u = re.sub(r'^https?://(www\.)?', '', u)
    return u.lower()

def source_priority(item):
    t = item.get("type", "")
    if t == "paper": return 0
    if t == "patent": return 1
    return 2

def deduplicate(items):
    if not items: return items, 0
    url_groups = {}
    for item in items:
        nurl = normalize_url(item.get("url", ""))
        if nurl in url_groups:
            existing = url_groups[nurl]
            if len(item.get("summary", "")) > len(existing.get("summary", "")):
                url_groups[nurl] = item
        else:
            url_groups[nurl] = item
    deduped = list(url_groups.values())
    final = []
    removed = 0
    for item in deduped:
        is_dup = False
        title_en = item.get("title_en", item.get("title", ""))
        for existing in final:
            existing_title = existing.get("title_en", existing.get("title", ""))
            if title_similarity(title_en, existing_title) >= 0.8:
                if source_priority(item) < source_priority(existing):
                    final.remove(existing)
                    final.append(item)
                is_dup = True
                break
        if not is_dup: final.append(item)
        else: removed += 1
    total_removed = len(items) - len(final)
    return final, total_removed

def to_noun_ending(text):
    text = text.rstrip(".")
    replacements = [
        (r'을 달성했다$', '을 달성'), (r'를 달성했다$', '를 달성'),
        (r'에 성공했다$', '에 성공'), (r'를 발표했다$', '를 발표'),
        (r'을 발표했다$', '을 발표'), (r'를 시작했다$', '를 시작'),
        (r'을 시작했다$', '을 시작'), (r'를 기록했다$', '를 기록'),
        (r'을 기록했다$', '을 기록'), (r'를 초과했다$', '를 초과'),
        (r'을 초과했다$', '을 초과'), (r'를 보였다$', '를 시현'),
        (r'을 보였다$', '을 시현'), (r'를 보여주었다$', '를 시현'),
        (r'을 보여주었다$', '을 시현'), (r'를 구현한다$', '를 구현'),
        (r'을 구현한다$', '을 구현'), (r'를 제안한다$', '를 제안'),
        (r'을 제안한다$', '을 제안'), (r'를 제공한다$', '를 제공'),
        (r'을 제공한다$', '을 제공'), (r'를 해결한다$', '를 해결'),
        (r'을 해결한다$', '을 해결'), (r'를 지원한다$', '를 지원'),
        (r'을 지원한다$', '을 지원'), (r'를 수행한다$', '를 수행'),
        (r'을 수행한다$', '을 수행'),
        (r'를 목표로 한다$', '를 목표'), (r'을 목표로 한다$', '을 목표'),
        (r'를 목표로 하고 있다$', '를 목표'),
        (r'가 가능하다$', '가 가능'), (r'이 가능하다$', '이 가능'),
        (r'고 있다$', '는 중'), (r'중이다$', '중'),
        (r'예정이다$', '예정'), (r'있었다$', '있음'),
        (r'되었다$', '됨'), (r'하였다$', ''),
        (r'했다$', ''), (r'였다$', ''), (r'이다$', ''),
        (r'한다$', ''), (r'된다$', ''), (r'난다$', ''),
    ]
    for pat, rep in replacements:
        new = re.sub(pat, rep, text)
        if new != text: return new.rstrip()
    return text

def process_summary(text):
    sentences = re.split(r'(?<=\.) ', text)
    result = []
    for s in sentences:
        s = s.strip().rstrip(".")
        s = to_noun_ending(s)
        if s: result.append(s)
    return ". ".join(result)

def split_summary(text, limit=60):
    text = process_summary(text)
    if len(text) <= limit: return text, ""
    sentences = text.split(". ")
    if len(sentences) > 1: return sentences[0], ". ".join(sentences[1:])
    return text[:limit], text[limit:]

def dedup_source_in_title(source, title):
    if not source: return title
    for sep in [", ", " "]:
        prefix = source + sep
        if title.startswith(prefix): return title[len(prefix):]
    return title

_field_id = [2000000000]
_field_seq = [627600491]
def next_field_id():
    _field_id[0] += 1
    return _field_id[0]

def make_url_para_with_link(url):
    fid = next_field_id()
    cmd_url = url.replace(":", "\\:") + ";1;0;0;"
    # Removed hp:linesegarray to allow HWP to calculate layout automatically
    return (
        '  <hp:p id="0" paraPrIDRef="35" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">\n'
        '    <hp:run charPrIDRef="32">\n'
        '      <hp:t>   \u203b </hp:t>\n'
        '      <hp:ctrl>\n'
        f'        <hp:fieldBegin id="{fid}" type="HYPERLINK" name="" editable="0" dirty="1" zorder="-1" fieldid="{_field_seq[0]}">\n'
        '          <hp:parameters cnt="6" name="">\n'
        '            <hp:integerParam name="Prop">0</hp:integerParam>\n'
        f'            <hp:stringParam name="Command">{esc(cmd_url)}</hp:stringParam>\n'
        f'            <hp:stringParam name="Path">{esc(url)}</hp:stringParam>\n'
        '            <hp:stringParam name="Category">HWPHYPERLINK_TYPE_URL</hp:stringParam>\n'
        '            <hp:stringParam name="TargetType">HWPHYPERLINK_TARGET_BOOKMARK</hp:stringParam>\n'
        '            <hp:stringParam name="DocOpenType">HWPHYPERLINK_JUMP_CURRENTTAB</hp:stringParam>\n'
        '          </hp:parameters>\n'
        '        </hp:fieldBegin>\n'
        '      </hp:ctrl>\n'
        f'      <hp:t>{esc(url)}</hp:t>\n'
        '      <hp:ctrl>\n'
        f'        <hp:fieldEnd beginIDRef="{fid}" fieldid="{_field_seq[0]}"/>\n'
        '      </hp:ctrl>\n'
        '    </hp:run>\n'
        '  </hp:p>'
    )

def make_entry(source, title, date_str, url, summary, detail=""):
    parts = date_str.split("-")
    mm_dd = f"{int(parts[1])}.{int(parts[2])}" if len(parts) == 3 else date_str
    lines = []
    # Paragraph 1: Source and Title
    lines.append(
        '  <hp:p id="0" paraPrIDRef="33" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">\n'
        '    <hp:run charPrIDRef="34">\n'
        f'      <hp:t> \u25a1 {esc(source)}, {esc(title)}</hp:t>\n'
        '    </hp:run>\n'
        '    <hp:run charPrIDRef="35">\n'
        f'      <hp:t>({esc(mm_dd)})</hp:t>\n'
        '    </hp:run>\n'
        '  </hp:p>'
    )
    # Paragraph 2: URL
    lines.append(make_url_para_with_link(url))
    # Paragraph 3: Summary
    lines.append(
        '  <hp:p id="0" paraPrIDRef="36" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">\n'
        '    <hp:run charPrIDRef="30">\n'
        f'      <hp:t>  \u25cb {esc(summary)}</hp:t>\n'
        '    </hp:run>\n'
        '  </hp:p>'
    )
    # Paragraph 4: Detail (if any)
    if detail:
        lines.append(
            '  <hp:p id="0" paraPrIDRef="36" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">\n'
            '    <hp:run charPrIDRef="30">\n'
            f'      <hp:t>    - {esc(detail)}</hp:t>\n'
            '    </hp:run>\n'
            '  </hp:p>'
        )
    return "\n".join(lines)

def empty_para():
    return (
        '  <hp:p id="0" paraPrIDRef="34" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">\n'
        '    <hp:run charPrIDRef="30"/>\n'
        '  </hp:p>'
    )

def build(template_path, output_path, items, today_str, title=None):
    with zipfile.ZipFile(template_path, "r") as zin:
        try:
            section_xml = zin.read("Contents/section0.xml").decode("utf-8")
            header_xml = zin.read("Contents/header.xml").decode("utf-8")
        except UnicodeDecodeError:
            section_xml = zin.read("Contents/section0.xml").decode("cp949", errors="ignore")
            header_xml = zin.read("Contents/header.xml").decode("cp949", errors="ignore")

    if title:
        section_xml = section_xml.replace("휴머노이드 분야 국내외 동향", title)

    marker = 'charPrIDRef="33"/>'
    idx = section_xml.find(marker)
    end_p = section_xml.find("</hp:p>", idx) + len("</hp:p>")
    header_part = section_xml[:end_p]

    # Minimal fix for spacing in specific body IDs only
    for cid in ["30", "34", "35", "36", "37", "38", "39"]:
        pattern = f'<hh:charPr id="{cid}"'
        pos = header_xml.find(pattern)
        if pos >= 0:
            sp_start = header_xml.find('<hh:spacing', pos)
            sp_end = header_xml.find('/>', sp_start) + 2
            if sp_start >= 0 and sp_start < pos + 500:
                new_spacing = '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                header_xml = header_xml[:sp_start] + new_spacing + header_xml[sp_end:]

    new_charpr = '''      <hh:charPr id="40" height="1200" textColor="#0000FF" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="2">
        <hh:fontRef hangul="4" latin="4" hanja="4" japanese="4" other="4" symbol="4" user="4"/>
        <hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:spacing hangul="-5" latin="-5" hanja="-5" japanese="-5" other="-5" symbol="-5" user="-5"/>
        <hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:underline type="BOTTOM" shape="SOLID" color="#0000FF"/>
        <hh:strikeout shape="NONE" color="#000000"/>
        <hh:outline type="NONE"/>
        <hh:shadow type="NONE" color="#B2B2B2" offsetX="10" offsetY="10"/>
      </hh:charPr>'''
    header_xml = header_xml.replace('itemCnt="40"', 'itemCnt="41"')
    header_xml = header_xml.replace('</hh:charProperties>', new_charpr + '\n    </hh:charProperties>')

    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    entries = [empty_para()]
    for item in items:
        summ, det = split_summary(item.get("summary", ""))
        title_clean = dedup_source_in_title(item.get("source", ""), item.get("title", ""))
        entries.append(make_entry(item.get("source", ""), title_clean, item.get("date", ""), item.get("url", ""), summ, det))
    entries.append(empty_para())

    new_section = header_part + "\n" + "\n".join(entries) + "\n</hs:sec>\n"
    new_section = new_section.replace("{오늘날짜YY.MM.DD}", today_str)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    tmp = output_path + ".tmp"
    with zipfile.ZipFile(template_path, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fname = item.filename
                if fname.lower() == "contents/section0.xml":
                    zout.writestr(item, new_section.encode("utf-8"))
                elif fname.lower() == "contents/header.xml":
                    zout.writestr(item, header_xml.encode("utf-8"))
                elif fname == "mimetype":
                    zout.writestr(item, zin.read(fname), compress_type=zipfile.ZIP_STORED)
                else:
                    zout.writestr(item, zin.read(fname))
    os.replace(tmp, output_path)
    return len(items)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--today", required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument("--dedup", action="store_true", default=True)
    parser.add_argument("--no-dedup", action="store_false", dest="dedup")
    args = parser.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        items = json.load(f)
    if args.dedup:
        items, _ = deduplicate(items)
    count = build(args.template, args.output, items, args.today, args.title)
    print(f"Generated: {args.output}")
