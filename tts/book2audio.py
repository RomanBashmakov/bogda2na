#!/usr/bin/env python3
"""Озвучка книг локальным ИИ: fb2/epub/txt -> mp3 по главам (Silero TTS).

Примеры (из корня проекта):
  tts/.venv/bin/python tts/book2audio.py книга.fb2
  tts/.venv/bin/python tts/book2audio.py книга.epub --voice kseniya
  tts/.venv/bin/python tts/book2audio.py роман.txt --rate 15
  tts/.venv/bin/python tts/book2audio.py --demo        # демо всех голосов

Шпаргалка с примерами: python3 tts/book2audio.py help
(она же показывается при запуске без аргументов).

Всё считается локально; интернет нужен один раз — при первом синтезе
Silero скачивает свои веса (~60 МБ) в ~/.cache/torch. Готовые главы
при повторном запуске пропускаются (--force — перегенерировать),
Ctrl-C — продолжение с места остановки.
"""

import argparse
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "out"

VOICES = [("aidar", "мужской"), ("baya", "женский"),
          ("kseniya", "женский"), ("xenia", "женский"),
          ("eugene", "мужской")]
DEFAULT_VOICE = "aidar"

SAMPLE_RATE = 24000      # Гц — то, что выдаёт Silero
MP3_BITRATE = "64k"      # моно-речи хватает с запасом
MAX_BATCH_CHARS = 900    # символов на один вызов модели
MIN_CHAPTER_CHARS = 60   # короче — не глава (обложки, оглавления)
TXT_CHUNK_CHARS = 9000   # кусок для txt без явных глав (~10 мин звучания)
SENT_BREAK = '<break time="200ms" />'   # пауза между предложениями
PARA_BREAK = '<break time="600ms" />'   # пауза между абзацами

DEMO_TEXT = ("В городе начиналось утро: хлопали двери подъездов, из пекарни "
             "тянуло свежим хлебом, и по мостовой простучал первый трамвай. "
             "Выходной обещал быть долгим — можно было не спешить.")

# ------------------------------------------------------------------ CLI ---

def print_help_card() -> None:
    """Короткая шпаргалка: примеры запуска, голоса, частые флаги, файлы."""
    py = sys.executable
    L = ["Озвучка книг локальным ИИ: fb2/epub/txt -> mp3 по главам (Silero)",
         "",
         "ЗАПУСК — примеры (из корня проекта):",
         f"  {py} tts/book2audio.py книга.fb2",
         f"  {py} tts/book2audio.py книга.epub --voice kseniya",
         f"  {py} tts/book2audio.py роман.txt --rate 15 --out роман",
         f"  {py} tts/book2audio.py --demo      # демо всех голосов",
         "",
         "ГОЛОСА (Silero, русский):"]
    for name, g in VOICES:
        d = " — по умолчанию" if name == DEFAULT_VOICE else ""
        L.append(f"  --voice {name:<10}{g}{d}")
    L += ["",
          "ЧАСТО ИСПОЛЬЗУЕТСЯ:",
          "  --voice ИМЯ     голос озвучки (список выше; --demo — послушать)",
          "  --rate N        темп в %: 20 быстрее, -20 медленнее (от -50 до 50)",
          "  --out ПАПКА     куда класть главы (по умолчанию tts/out/<книга>)",
          "  --force         перегенерировать и уже готовые главы",
          "  --device cpu    считать на CPU (по умолчанию сама выберет GPU)",
          "",
          "ФАЙЛЫ:",
          "  tts/out/<книга>/01 - <глава>.mp3 ...   главы по порядку",
          "  tts/out/demo/<голос>.mp3               демо голосов (--demo)",
          "  ~/.cache/torch/                        веса Silero (качаются раз)",
          "",
          "Готовые главы пропускаются при повторном запуске.",
          "Полный список параметров: python3 tts/book2audio.py --help"]
    print("\n".join(L))


def parse_args(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] == "help":
        print_help_card()
        raise SystemExit(0)
    p = argparse.ArgumentParser(
        prog="book2audio.py",
        description="Озвучка книг локальным Silero TTS: "
                    "fb2/epub/txt -> папка mp3 по главам.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("book", nargs="?", default=None,
                   help="файл книги: .fb2, .epub или .txt")
    p.add_argument("--voice", default=DEFAULT_VOICE,
                   choices=[v[0] for v in VOICES],
                   help="голос озвучки (--demo — послушать все)")
    p.add_argument("--rate", type=int, default=0,
                   help="темп речи в %%: 20 — быстрее, -20 — медленнее")
    p.add_argument("--out", type=Path, default=None,
                   help="папка результата; относительная — внутри tts/out/")
    p.add_argument("--device", choices=["cpu", "cuda"], default=None,
                   help="считать на CPU/GPU (по умолчанию: авто)")
    p.add_argument("--force", action="store_true",
                   help="перегенерировать и уже готовые главы")
    p.add_argument("--demo", action="store_true",
                   help="записать демо-абзац каждым голосом в out/demo/")
    p.add_argument("--list-voices", action="store_true",
                   help="просто список голосов")
    a = p.parse_args(args)
    if a.list_voices:
        for name, g in VOICES:
            d = " — по умолчанию" if name == DEFAULT_VOICE else ""
            print(f"{name:<10} {g}{d}")
        raise SystemExit(0)
    if not a.demo and not a.book:
        p.error("укажите файл книги (.fb2/.epub/.txt) или --demo")
    if not -50 <= a.rate <= 50:
        p.error("--rate: от -50 до 50")
    return a


def main(argv=None):
    args = parse_args(argv)
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nПрервано. Готовые главы сохранены — повторный запуск "
              "продолжит с места остановки.")
        raise SystemExit(130)


# ---------------------------------------------------------------- текст ---

BAD_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
FOOTNOTES = re.compile(r"\[\d{1,3}\]")
SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[«\"„(А-ЯЁA-Z0-9])")


def clean_paragraph(p: str) -> str:
    """Один абзац -> чистая строка (без сносок [12], лишних пробелов)."""
    p = BAD_CTRL.sub(" ", p)
    p = FOOTNOTES.sub("", p)
    p = re.sub(r"[ \t\u00a0]+", " ", p)
    return p.strip()


def sanitize_name(s: str, maxlen: int = 60) -> str:
    """Строка -> безопасная часть имени файла."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", s)
    s = re.sub(r"\s+", " ", s).strip().strip(". ")
    return s[:maxlen].rstrip() or "Без названия"


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def paragraphs_from_plain(text: str) -> list:
    """Сплошной текст -> список абзацев (склейка переносов строк)."""
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"([а-яёa-z])-\n(?=[а-яёa-z])", r"\1", text)  # пере-носы
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)  # строка внутри абзаца
    out = []
    for block in re.split(r"\n{2,}", text):
        p = clean_paragraph(block)
        if p:
            out.append(p)
    return out


def paragraphs_to_batches(paragraphs: list) -> list:
    """Абзацы -> пакеты [(предложение, начинает_абзац), ...] <= MAX_BATCH."""
    flat = []
    for p in paragraphs:
        first = True
        for s in SENT_SPLIT.split(p):
            s = s.strip()
            if s:
                flat.append((s, first))
                first = False
    batches, cur, cur_len = [], [], 0
    for s, new_par in flat:
        sep = PARA_BREAK if new_par else SENT_BREAK
        if cur and cur_len + len(sep) + len(s) > MAX_BATCH_CHARS:
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append((s, new_par))
        cur_len += len(s) + (len(sep) if len(cur) > 1 else 0)
    if cur:
        batches.append(cur)
    return batches


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_ssml(batch: list) -> str:
    """Пакет предложений -> SSML с паузами между предложениями/абзацами."""
    parts = []
    for i, (s, new_par) in enumerate(batch):
        if i:
            parts.append(PARA_BREAK if new_par else SENT_BREAK)
        parts.append(_esc(s))
    return "<speak>" + "".join(parts) + "</speak>"


# ----------------------------------------------------------------- fb2 ---

def _local(tag) -> str:
    """'{ns}title' -> 'title' — работаем без оглядки на пространства имён."""
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _el_text(el) -> str:
    return " ".join(t.strip() for t in el.itertext() if t and t.strip())


def parse_fb2(path: Path):
    raw = path.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        try:
            root = ET.fromstring(BAD_CTRL.sub(b" ", raw))
        except ET.ParseError as e:
            raise SystemExit(f"fb2 не читается как XML ({e}). Откройте файл "
                             "в читалке и пересохраните или дайте txt/epub.")
    author, title = "", ""
    for el in root.iter():
        if _local(el.tag) == "title-info":
            for sub in el:
                if _local(sub.tag) == "book-title":
                    title = _el_text(sub)
                elif _local(sub.tag) == "author":
                    names = (_el_text(c) for c in sub if _local(c.tag)
                             in ("first-name", "last-name", "nickname"))
                    author = " ".join(n for n in names if n)
            break
    chapters = []

    def walk_section(sec, default_title):
        head, paras, nested = "", [], []
        for child in sec:
            t = _local(child.tag)
            if t == "title" and not head:
                head = _el_text(child)
            elif t in ("p", "subtitle", "v", "text-author"):
                txt = _el_text(child)
                if txt:
                    paras.append(txt)
            elif t == "poem":                      # стихи — по строчкам
                for v in child.iter():
                    if _local(v.tag) in ("v", "text-author"):
                        txt = _el_text(v)
                        if txt:
                            paras.append(txt)
            elif t == "section":
                nested.append(child)
        if paras:
            chapters.append((head or default_title, paras))
        for i, sub_sec in enumerate(nested, 1):
            walk_section(sub_sec, f"{default_title}.{i}")

    body = None
    for b in root:                                  # тело без сносок
        if _local(b.tag) == "body" and b.attrib.get("name") != "notes":
            body = b
            break
    if body is None:
        for b in root:
            if _local(b.tag) == "body":
                body = b
                break
    intro = []
    if body is not None:
        for child in body:
            t = _local(child.tag)
            if t == "section":
                walk_section(child, f"Часть {len(chapters) + 1}")
            elif t in ("p", "subtitle", "v") and _el_text(child):
                intro.append(_el_text(child))
    if intro:
        chapters.insert(0, ("Вступление", intro))
    return author, title, chapters


# ---------------------------------------------------------------- epub ---

class _HTMLText(HTMLParser):
    """XHTML из epub -> [(это_заголовок, текст), ...]."""

    BLOCKS = {"p", "div", "li", "tr", "blockquote", "section", "article",
              "header", "footer", "figcaption", "ul", "ol", "table"}
    HEADS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._buf, self._head, self._skip = [], False, 0

    def _flush(self):
        text = clean_paragraph("".join(self._buf))
        self._buf = []
        if text:
            self.parts.append((self._head, text))

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif self._skip:
            return
        elif tag in self.BLOCKS or tag in self.HEADS or tag == "br":
            self._flush()
            self._head = tag in self.HEADS

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif not self._skip and (tag in self.BLOCKS or tag in self.HEADS):
            self._flush()
            self._head = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self._buf.append(data)

    def result(self):
        self.close()
        self._flush()
        return self.parts


def _read_xml(zf, name):
    data = zf.read(name)
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return ET.fromstring(BAD_CTRL.sub(b" ", data))


def _find_opf(zf) -> str:
    try:
        for el in _read_xml(zf, "META-INF/container.xml").iter():
            if _local(el.tag) == "rootfile" and el.attrib.get("full-path"):
                return el.attrib["full-path"]
    except (KeyError, ET.ParseError):
        pass
    for n in zf.namelist():
        if n.lower().endswith(".opf"):
            return n
    raise SystemExit("В epub не найден файл описания (.opf) — файл битый?")


def _resolve(base: str, href: str, names: set) -> str:
    href = unquote(href.split("#")[0])
    cand = posixpath.normpath(posixpath.join(base, href)) if base \
        else posixpath.normpath(href)
    cand = cand.lstrip("/")
    if cand in names:
        return cand
    low = {n.lower(): n for n in names}
    return low.get(cand.lower(), "")


def parse_epub(path: Path):
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        opf_path = _find_opf(zf)
        base = str(Path(opf_path).parent)
        manifest, spine, title, author = {}, [], "", ""
        for el in _read_xml(zf, opf_path).iter():
            t = _local(el.tag)
            if t == "item" and el.attrib.get("id"):
                manifest[el.attrib["id"]] = el.attrib
            elif t == "itemref" and el.attrib.get("idref"):
                spine.append(el.attrib["idref"])
            elif t == "title" and not title:
                title = _el_text(el)
            elif t == "creator" and not author:
                author = _el_text(el)
        chapters, n = [], 0
        for idref in spine:
            item = manifest.get(idref)
            if not item:
                continue
            media = (item.get("media-type") or "").lower()
            if media and "html" not in media and "xml" not in media:
                continue
            full = _resolve(base, item.get("href", ""), names)
            if not full:
                continue
            try:
                data = zf.read(full)
            except KeyError:
                continue
            parser = _HTMLText()
            parser.feed(data.decode("utf-8", "replace"))
            parts = parser.result()
            if not parts:
                continue
            head = next((t for is_h, t in parts if is_h), "")
            paras = [t for _, t in parts]
            if chapters and sum(map(len, paras)) < MIN_CHAPTER_CHARS:
                chapters[-1][1].extend(paras)   # крохи — в прошлую главу
                continue
            n += 1
            chapters.append((head or f"Часть {n}", paras))
        return author, title, chapters


# ----------------------------------------------------------------- txt ---

CHAPTER_RE = re.compile(
    r"^\s*(?:глава|часть|пролог|эпилог|предисловие|послесловие|"
    r"chapter|part|prologue|epilogue)\b[^{}<>]{0,60}$",
    re.IGNORECASE)


def parse_txt(path: Path):
    text = read_text_file(path)
    chapters, head, buf = [], "Начало", []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if CHAPTER_RE.match(line) and len(line.strip()) <= 70:
            chapters.append((head, buf))
            head, buf = line.strip(), []
        else:
            buf.append(line)
    chapters.append((head, buf))
    found = [(t, paragraphs_from_plain("\n".join(b))) for t, b in chapters]
    found = [(t, ps) for t, ps in found if ps]
    if len(found) >= 2:
        return found
    # явных глав нет — резать на куски ~TXT_CHUNK_CHARS по границам абзацев
    paras = paragraphs_from_plain(text)
    chunks, cur, size = [], [], 0
    for p in paras:
        cur.append(p)
        size += len(p)
        if size >= TXT_CHUNK_CHARS:
            chunks.append(cur)
            cur, size = [], 0
    if cur:
        if chunks and sum(map(len, cur)) < TXT_CHUNK_CHARS // 3:
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    return [(f"Часть {i + 1}", ch) for i, ch in enumerate(chunks)]


def load_book(path: Path):
    ext = path.suffix.lower()
    if ext == ".fb2":
        author, title, chapters = parse_fb2(path)
    elif ext == ".epub":
        author, title, chapters = parse_epub(path)
    elif ext == ".txt":
        author, title, chapters = "", path.stem, parse_txt(path)
    else:
        raise SystemExit(f"Не знаю формат «{ext or path.name}» — "
                         "нужен .fb2, .epub или .txt.")
    chapters = [(t, ps) for t, ps in chapters
                if sum(map(len, ps)) >= MIN_CHAPTER_CHARS]
    if not chapters:
        raise SystemExit("Не нашлось ни одной главы с текстом — "
                         "проверьте файл.")
    return author, title or path.stem, chapters


# --------------------------------------------------------------- синтез ---

def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit("ffmpeg не найден. Поставьте: sudo apt install ffmpeg "
                         "(или pip install imageio-ffmpeg в tts/.venv).")


def load_tts(device):
    try:
        import torch
    except ImportError:
        raise SystemExit("PyTorch не найден — сначала настройте окружение: "
                         "bash tts/setup.sh")
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _ = torch.hub.load("snakers4/silero-models", "silero_tts",
                              language="ru", speaker="v4_ru",
                              skip_validation=True)
    model.to(device)
    if device == "cpu":
        torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
    return model, device


def tts_ssml(model, device, ssml, voice):
    import torch
    with torch.no_grad():
        return model.apply_tts(ssml_text=ssml, speaker=voice,
                               sample_rate=SAMPLE_RATE,
                               put_accent=True, put_yo=True)


class Mp3Writer:
    """Принимает torch-тензоры аудио -> mp3 с id3-тегами (ffmpeg)."""

    def __init__(self, path, title, artist, album, track, tracks, tempo=1.0):
        self.path = path
        args = [find_ffmpeg(), "-y", "-loglevel", "error",
                "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1",
                "-i", "pipe:0"]
        if abs(tempo - 1.0) > 1e-6:            # --rate: темп через atempo
            args += ["-filter:a", f"atempo={tempo:.4f}"]
        args += ["-codec:a", "libmp3lame", "-b:a", MP3_BITRATE,
                 "-metadata", f"title={title}",
                 "-metadata", f"artist={artist}",
                 "-metadata", f"album={album}",
                 "-metadata", f"track={track}/{tracks}",
                 "-id3v2_version", "3", "-f", "mp3", str(path)]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE)

    def write(self, audio) -> None:
        import numpy as np
        pcm = (audio.detach().cpu().numpy().clip(-1, 1) * 32767).astype("<i2")
        self.proc.stdin.write(pcm.tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise SystemExit(f"ffmpeg не собрал файл {self.path}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            self.proc.kill()
            self.proc.wait()


def synth_chapter(model, device, voice, paras, writer) -> float:
    """Озвучить главу в writer; вернуть длительность в секундах."""
    samples = 0
    for batch in paragraphs_to_batches(paras):
        audio = tts_ssml(model, device, make_ssml(batch), voice)
        writer.write(audio)
        samples += int(audio.shape[-1])
    return samples / SAMPLE_RATE


# --------------------------------------------------------------- запуск ---

def run(args):
    if args.demo:
        return run_demo(args)
    path = Path(args.book)
    if not path.is_file():
        raise SystemExit(f"Файл не найден: {path}")
    author, title, chapters = load_book(path)
    out_dir = args.out or (OUT_DIR / sanitize_name(title, 70))
    if not out_dir.is_absolute():
        out_dir = OUT_DIR / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Книга: {title}" + (f" — {author}" if author else ""))
    print(f"Глав: {len(chapters)}   Папка: {out_dir}")
    model, device = load_tts(args.device)
    extra = f", темп {args.rate:+d}%" if args.rate else ""
    print(f"Устройство: {'GPU (cuda)' if device == 'cuda' else 'CPU'}; "
          f"голос: {args.voice}{extra}")
    tempo = 1 + args.rate / 100
    made, skipped, minutes = 0, 0, 0.0
    total = len(chapters)
    for i, (ctitle, paras) in enumerate(chapters, 1):
        fname = out_dir / f"{i:02d} - {sanitize_name(ctitle)}.mp3"
        if fname.exists() and not args.force:
            print(f"  [{i}/{total}] {fname.name} — уже есть, пропускаю")
            skipped += 1
            continue
        part = fname.with_name(fname.name + ".part")   # чтобы не остался
        t0 = time.time()                                # битый mp3 при Ctrl-C
        with Mp3Writer(part, title=ctitle, artist=author or "Silero TTS",
                       album=title, track=i, tracks=total, tempo=tempo) as w:
            secs = synth_chapter(model, device, args.voice, paras, w)
        part.replace(fname)
        minutes += secs / 60
        made += 1
        print(f"  [{i}/{total}] {fname.name} — {secs / 60:.1f} мин звука "
              f"за {time.time() - t0:.0f} с")
    print(f"\nГотово: озвучено {made} гл. ({minutes:.0f} мин текста), "
          f"пропущено {skipped}.")
    print(f"Папка: {out_dir}")


def run_demo(args):
    out = OUT_DIR / "demo"
    out.mkdir(parents=True, exist_ok=True)
    model, device = load_tts(args.device)
    print(f"Устройство: {'GPU (cuda)' if device == 'cuda' else 'CPU'}")
    paras = [DEMO_TEXT]
    for i, (voice, _g) in enumerate(VOICES, 1):
        f = out / f"{voice}.mp3"
        with Mp3Writer(f, title=f"Демо голоса {voice}", artist="Silero TTS",
                       album="Демо голосов Silero", track=i,
                       tracks=len(VOICES)) as w:
            synth_chapter(model, device, voice, paras, w)
        print(f"  {f}")
    print("\nПослушайте файлы и выберите голос, наприм.: "
          "tts/.venv/bin/python tts/book2audio.py книга.fb2 --voice kseniya")


if __name__ == "__main__":
    main()