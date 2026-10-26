import json, glob, re

HEX = re.compile(r'#[0-9A-Fa-f]{3,8}')
files = sorted(glob.glob('painter/schemes/*.json')) + sorted(glob.glob('Pixel_Art/*.json'))
for f in files:
    try:
        d = json.load(open(f, encoding='utf-8'))
    except Exception as e:
        print('JSON ERR', f, e)
        continue
    cols, rows = d.get('cols'), d.get('rows')
    colors = d.get('colors') or []
    cells = d.get('cells') or []
    ncol = len(colors)
    errs = []
    if not isinstance(cells, list) or len(cells) != cols * rows:
        errs.append('len %s != %s*%s' % (len(cells), cols, rows))

    def ok(v):
        return isinstance(v, int) and not isinstance(v, bool) and -1 <= v < ncol

    bad = [(i, repr(v)) for i, v in enumerate(cells) if not ok(v)][:5]
    nbad = sum(1 for v in cells if not ok(v))
    if bad:
        errs.append('bad values x%d: %s' % (nbad, bad))
    if not isinstance(colors, list) or not 1 <= ncol <= 64:
        errs.append('ncolors=%d' % ncol)
    for c in colors:
        if not isinstance(c, dict) or not HEX.fullmatch(str(c.get('hex', ''))):
            errs.append('bad hex %r' % (c,))
            break
    if errs:
        print('BAD', f, '|', '; '.join(errs))
print('checked all')
