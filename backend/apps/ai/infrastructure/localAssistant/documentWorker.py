"""Isolated, bounded text extraction worker; not a web endpoint. No OCR or tools."""
import io
import json
import sys
import zipfile
import xml.etree.ElementTree as ET

LIMIT = 4 * 1024 * 1024

def fragmented_pdf_text(text):
    lines = [line.strip() for line in text.splitlines() if any(c.isalpha() for c in line)]
    return len(lines) >= 12 and sum(len(line) == 1 for line in lines) / len(lines) >= 0.6

def pdf_grid_tables(page, textpage):
    """Conservative ruled rectangular grids only; cells come from PDF coordinates, not an LLM."""
    import ctypes as c
    import pypdfium2 as pdfium
    import math
    identity = (1.,0.,0.,1.,0.,0.)
    def compose(p,q):
        a,b,cc,d,e,f=p;g,h,i,j,k,l=q
        return (a*g+cc*h,b*g+d*h,a*i+cc*j,b*i+d*j,a*k+cc*l+e,b*k+d*l+f)
    def matrix(obj):
        m=obj.get_matrix();return (m.a,m.b,m.c,m.d,m.e,m.f)
    def point(m,x,y):return (m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5])
    def clustered(values):
        groups=[]
        for v in sorted(values):
            if groups and v-groups[-1][-1] <= 1.2:groups[-1].append(v)
            else:groups.append([v])
        return [sum(g)/len(g) for g in groups]
    hs=[];vs=[];ancestors={}
    for count,obj in enumerate(page.get_objects(max_depth=5)):
        if count>=2500:return []
        parent=ancestors.get(obj.level-1,identity) if obj.level else identity
        m=compose(parent,matrix(obj))
        if obj.type==pdfium.raw.FPDF_PAGEOBJ_FORM:
            ancestors[obj.level]=m;continue
        if obj.type!=pdfium.raw.FPDF_PAGEOBJ_PATH:continue
        size=pdfium.raw.FPDFPath_CountSegments(obj.raw)
        if not 2<=size<=100:continue
        points=[];curved=False
        for n in range(size):
            seg=pdfium.raw.FPDFPath_GetPathSegment(obj.raw,n)
            kind=pdfium.raw.FPDFPathSegment_GetType(seg)
            if kind not in (0,2):curved=True;break
            x=c.c_float();y=c.c_float()
            if not pdfium.raw.FPDFPathSegment_GetPoint(seg,c.byref(x),c.byref(y)):curved=True;break
            xx,yy=point(m,x.value,y.value)
            if not math.isfinite(xx) or not math.isfinite(yy):curved=True;break
            points.append((kind,xx,yy,bool(pdfium.raw.FPDFPathSegment_GetClose(seg))))
        if curved:continue
        xs=[p[1] for p in points];ys=[p[2] for p in points]
        left,right=min(xs),max(xs);bottom,top=min(ys),max(ys)
        # A thin filled rectangle is a rule, represented by its centreline.
        rectangular=(len(points) in (4,5) and all(min(abs(x-left),abs(x-right))<.1 and min(abs(y-bottom),abs(y-top))<.1 for _,x,y,_ in points))
        if rectangular and right-left<=2 and top-bottom>=12:vs.append(((left+right)/2,bottom,top));continue
        if rectangular and top-bottom<=2 and right-left>=12:hs.append(((bottom+top)/2,left,right));continue
        previous=None;start=None
        for kind,x,y,close in points:
            if kind==2:start=(x,y);previous=start;continue
            if previous:
                px,py=previous
                if abs(y-py)<.15 and abs(x-px)>=12:hs.append(((y+py)/2,min(x,px),max(x,px)))
                if abs(x-px)<.15 and abs(y-py)>=12:vs.append(((x+px)/2,min(y,py),max(y,py)))
            previous=(x,y)
            if close and start and previous!=start:
                px,py=start
                if abs(y-py)<.15 and abs(x-px)>=12:hs.append(((y+py)/2,min(x,px),max(x,px)))
                if abs(x-px)<.15 and abs(y-py)>=12:vs.append(((x+px)/2,min(y,py),max(y,py)))
        if len(hs)+len(vs)>1200:return []
    groups=[]
    for y,left,right in hs:
        if right-left<180:continue
        group=next((g for g in groups if abs(g[0]-left)<=2 and abs(g[1]-right)<=2),None)
        if group is None:group=[left,right,[]];groups.append(group)
        group[2].append(y)
    tables=[];used_bytes=0
    for left,right,heights in groups:
        ys=sorted(clustered(heights),reverse=True)
        bands=[]
        for top,bottom in zip(ys,ys[1:]):
            if not 8<=top-bottom<=180:bands.append(None);continue
            xs=clustered(x for x,lo,hi in vs if left-2<=x<=right+2 and lo<=bottom+1.5 and hi>=top-1.5)
            if not 3<=len(xs)<=13 or abs(xs[0]-left)>2 or abs(xs[-1]-right)>2 or any(b-a<8 for a,b in zip(xs,xs[1:])):bands.append(None);continue
            bands.append((top,bottom,xs))
        runs=[]
        for band in bands:
            if band is None:
                if runs and runs[-1]:runs.append([])
                continue
            if not runs or not runs[-1]:runs.append([band]);continue
            prev=runs[-1][-1]
            if abs(prev[1]-band[0])<=1.5 and len(prev[2])==len(band[2]) and all(abs(a-b)<=1.5 for a,b in zip(prev[2],band[2])):runs[-1].append(band)
            else:runs.append([band])
        for run in runs:
            if not 2<=len(run)<=13:continue
            if (len(run)-1)*(len(run[0][2])-1)>120:continue
            cells=[];valid=True
            for top,bottom,xs in run:
                row=[]
                for x1,x2 in zip(xs,xs[1:]):
                    text=' '.join(textpage.get_text_bounded(left=x1+1.2,bottom=bottom+1.2,right=x2-1.2,top=top-1.2).split())
                    if len(text)>160 or fragmented_pdf_text(text):valid=False;break
                    row.append(text)
                if not valid:break
                cells.append(row)
            if not valid:continue
            headers=cells[0]
            if sum(bool(s) for s in headers)<max(2,len(headers)*.6) or sum(any(c.isalpha() for c in s) for s in headers)<max(2,len(headers)*.7):continue
            import re
            known={'ردیف','شماره','شرح','مقدار','تعداد','واحد','علت','محل','تاریخ','نام','کد','مبلغ','قیمت','جمع','توضیحات','عنوان','ساعت','item','quantity','description','amount','date','name','code','price','total','unit','row','value','number'}
            labels=[set(re.findall(r'[\w\u0600-\u06ff]+',v.lower().replace('ي','ی').replace('ك','ک'))) for v in headers]
            if sum(bool(words & known) for words in labels)<2:continue
            alpha=[c for s in headers for c in s if c.isalpha()]
            rtl=bool(alpha) and sum('\u0600'<=c<='\u06ff' for c in alpha)/len(alpha)>.5
            if rtl:cells=[list(reversed(row)) for row in cells]
            table={'headers':cells[0],'rows':cells[1:],'direction':'rtl' if rtl else 'ltr'}
            cost=len(json.dumps(table,ensure_ascii=False).encode('utf-8'))
            if used_bytes+cost>6000:continue
            used_bytes+=cost;tables.append(table)
            if len(tables)>=2:return tables
    return tables


def valid_tables(value):
    """Validate bounded worker data again at the process boundary."""
    if not isinstance(value,list) or len(value)>2:return []
    result=[];used=0
    for table in value:
        if not isinstance(table,dict) or set(table)!={'headers','rows','direction'}:return []
        headers=table['headers'];rows=table['rows']
        if table['direction'] not in ('rtl','ltr') or not isinstance(headers,list) or not 2<=len(headers)<=12 or not isinstance(rows,list) or not 1<=len(rows)<=12:return []
        if any(not isinstance(row,list) or len(row)!=len(headers) for row in rows):return []
        if len(headers)*len(rows)>120 or any(not isinstance(cell,str) or len(cell)>160 for row in [headers]+rows for cell in row):return []
        used+=len(json.dumps(table,ensure_ascii=False).encode('utf-8'))
        if used>6000:return []
        result.append(table)
    return result


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
        # Preserve the original policy: no password-protected PDFs, even empty passwords.
        if PdfReader(io.BytesIO(data), strict=True).is_encrypted:
            raise ValueError('Encrypted PDF')
        import pypdfium2 as pdfium
        segments = []
        remaining = 32000
        with pdfium.PdfDocument(data) as document:
            for i in range(min(len(document), 15)):
                if remaining <= 0:
                    break
                page = document[i]
                try:
                    textpage = page.get_textpage()
                    try:
                        # Do not reconstruct RTL letters or table cells by guessing.
                        text = textpage.get_text_bounded().replace('\r\n', '\n').replace('\r', '\n')[:remaining]
                        try:
                            tables = valid_tables(pdf_grid_tables(page, textpage))
                        except Exception:
                            tables = []
                    finally:
                        textpage.close()
                finally:
                    page.close()
                if fragmented_pdf_text(text):
                    raise ValueError('Unreliable PDF text')
                remaining -= len(text)
                segments.append({'page': i + 1, 'text': text, 'tables': tables})
        return segments
    raise ValueError('Unsupported format')

if __name__ == '__main__':
    try:
        if sys.platform != 'win32':
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        if len(sys.argv) == 4 and sys.argv[1] == '.pdf':
            from pathlib import Path
            for name, directory in zip(('pypdfium2','pypdf'),sys.argv[2:]):
                packages = Path(directory).resolve()
                if not (packages / name / '__init__.py').is_file():
                    raise ValueError('Parser package unavailable')
                sys.path.insert(0, str(packages))
        raw = sys.stdin.buffer.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('File too large')
        result = extract(raw, sys.argv[1])
        # Pipes use a Windows code page by default; bypass text stdout encoding.
        sys.stdout.buffer.write(json.dumps({'segments': result}, ensure_ascii=False).encode('utf-8') + b'\n')
    except Exception:
        # No raw exception/file contents on stderr or in the API response.
        print(json.dumps({'segments': [], 'unreadable': True}))
        sys.exit(1)
