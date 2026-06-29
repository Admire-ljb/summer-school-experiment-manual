from __future__ import annotations

import html
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageOps = None


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT.parent / "\u5b9e\u9a8c\u624b\u518c"
ASSET_DIR = ROOT / "assets"
ASSET_SOURCE_DIR = ASSET_DIR / "source"
IMAGE_DIR = ASSET_DIR / "images"
IMAGE_EN_DIR = ASSET_DIR / "images-en"
IMAGE_EN_CURATED_DIR = ASSET_DIR / "images-en-curated"
TRANSLATION_CACHE = ROOT / "tools" / "translation-cache.zh-en.json"
IMAGE_OCR_CACHE = ROOT / "tools" / "image-ocr-cache.json"
FINAL_TEST_SLUG = "manual-13-project-demo"
FINAL_TEST_IMAGE_NAME = "final-comprehensive-test.png"
FINAL_TEST_ZH_SOURCE = ASSET_SOURCE_DIR / "manual-13-final-comprehensive-test-zh.png"
FINAL_TEST_EN_SOURCE = ASSET_SOURCE_DIR / "manual-13-final-comprehensive-test-en.png"
MAX_IMAGE_WIDTH = 1440
MAX_IMAGE_HEIGHT = 1200
OCR_MAX_IMAGE_SIDE = 800

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


@dataclass(frozen=True)
class Manual:
    slug: str
    number: int
    zh_title: str
    en_title: str
    source_name: str
    purpose: str
    preparation: tuple[str, ...]
    procedure: tuple[str, ...]
    verification: tuple[str, ...]


@dataclass(frozen=True)
class ParagraphBlock:
    text: str
    style: str
    images: tuple[str, ...]


@dataclass(frozen=True)
class TableBlock:
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class HeadingInfo:
    level: int
    zh_text: str
    en_source: str | None = None
    en_prefix: str = ""
    en_suffix: str = ""
    en_text: str | None = None


Block = ParagraphBlock | TableBlock


MANUALS = [
    Manual("manual-01-vm", 1, "\u5b89\u88c5\u914d\u7f6e\u865a\u62df\u673a", "Virtual Machine Installation and Configuration", "Day1_\u5b9e\u9a8c\u624b\u518c1-\u5b89\u88c5\u914d\u7f6e\u865a\u62df\u673a.docx", "Configure VMware Workstation and install Ubuntu 20.04 as the standard operating environment for all subsequent experiments.", ("Windows host computer with sufficient memory and disk space.", "VMware Workstation Pro 16 installation package.", "Ubuntu 20.04 LTS desktop image."), ("Install VMware Workstation and verify that the new virtual-machine wizard is available.", "Create an Ubuntu virtual machine with appropriate CPU, memory, disk, and NAT network settings.", "Install Ubuntu, perform first-boot setup, install VMware Tools, and create a clean snapshot."), ("Confirm network access from Ubuntu.", "Verify screen scaling and host-to-guest file transfer.", "Restore the clean snapshot once to confirm recovery is available.")),
    Manual("manual-02-ros", 2, "\u914d\u7f6e\u8ba4\u77e5 ROS", "ROS Configuration and Basic Concepts", "Day1_\u5b9e\u9a8c\u624b\u518c2-\u914d\u7f6e\u8ba4\u77e5ROS.docx", "Install ROS and establish the basic concepts used by later robot-control experiments.", ("Ubuntu virtual machine from Manual 1.", "Network access for package installation.", "Terminal access and basic Linux command familiarity."), ("Install ROS using the documented installation path or classroom script.", "Start roscore and run turtlesim-related commands.", "Use ROS tools to inspect nodes, topics, graphs, and message data."), ("Explain package, node, topic, publisher, and subscriber roles.", "Run turtlesim and teleoperation successfully.", "Use rqt_graph, rqt_plot, rosnode, and rostopic for observation.")),
    Manual("manual-03-crazyflie-setup", 3, "\u521d\u6b21\u914d\u7f6e\u4e0e\u9a71\u52a8 Crazyflie \u65e0\u4eba\u673a", "Initial Crazyflie Configuration and Operation", "Day1_\u5b9e\u9a8c\u624b\u518c3-\u521d\u6b21\u914d\u7f6e\u4e0e\u9a71\u52a8crazyfile\u65e0\u4eba\u673a.docx", "Prepare the Crazyflie software and hardware connection path for safe first operation.", ("Ubuntu/ROS environment from the previous manuals.", "Crazyflie aircraft, battery, USB cable, and Crazyradio.", "cflib, Crazyflie client, and required Python dependencies."), ("Install the Crazyflie client and required libraries.", "Configure USB permissions and radio connection settings.", "Connect to the aircraft and run conservative first-control tests."), ("Crazyflie client starts correctly.", "USB and radio connection can detect the aircraft.", "A short scripted test can be explained and stopped safely.")),
    Manual("manual-04-multiranger", 4, "multiranger", "Multi-ranger Sensor Experiment", "Day2_\u5b9e\u9a8c\u624b\u518c1-multiranger.docx", "Read multi-direction distance measurements and connect sensor readings to basic flight behavior.", ("Crazyflie with Multi-ranger deck.", "Working cflib environment.", "Clear indoor test area with simple obstacles."), ("Connect to Crazyflie through cflib.", "Read front, back, left, right, up, and down range values.", "Use threshold rules to generate simple reactive movement."), ("Range values change consistently when obstacles move.", "Students can identify which sensor direction triggered a response.", "The reactive behavior remains inside the safety area.")),
    Manual("manual-05-ranging", 5, "\u6d4b\u8ddd\u8fdb\u9636", "Advanced Ranging Experiment", "Day2_\u5b9e\u9a8c\u624b\u518c2-\u6d4b\u8ddd\u8fdb\u9636.docx", "Extend basic range reading into mission rules and obstacle-aware flight actions.", ("Crazyflie and Multi-ranger deck.", "Validated range-reading script.", "Instructor-confirmed test area."), ("Collect range readings under several obstacle configurations.", "Implement obstacle-triggered actions such as landing, backing away, or bouncing.", "Adjust thresholds and speeds conservatively."), ("The program exits through a safe stop condition.", "Sensor logs support the observed behavior.", "The selected thresholds can be justified from the measurements.")),
    Manual("manual-06-complex-map", 6, "\u590d\u6742\u5730\u56fe\u98de\u884c\u4e0e\u5efa\u56fe", "Complex-map Flight and Mapping", "Day2_\u5b9e\u9a8c\u624b\u518c3-\u590d\u6742\u5730\u56fe\u98de\u884c\u4e0e\u5efa\u56fe.docx", "Use controlled flight and range sensing to explore a more complex obstacle map.", ("Prepared obstacle area.", "Crazyflie with relevant sensing deck.", "Mapping or logging script from the manual."), ("Inspect the map constraints and permitted flight area.", "Run the flight or mapping procedure slowly enough for stable data collection.", "Review the generated obstacle points or map-like output."), ("The flight remains within the allowed area.", "The map output reflects major walls or obstacle regions.", "Failure cases are documented with likely causes.")),
    Manual("manual-07-autonomous-mapping-review", 7, "\u81ea\u4e3b\u5efa\u56fe+\u590d\u4e60", "Autonomous Mapping and Review", "Day2_\u5b9e\u9a8c\u624b\u518c4-\u81ea\u4e3b\u5efa\u56fe+\u590d\u4e60.docx", "Consolidate the ranging and mapping workflow through an autonomous mapping review task.", ("Completed range-sensing and mapping exercises.", "Known test area and flight restrictions.", "Team notes from previous experiments."), ("Review connection, sensing, control, and mapping requirements.", "Design or modify a route that samples useful map areas.", "Run the autonomous mapping task and record the result."), ("The route is reproducible.", "The produced map or log supports the route explanation.", "Main risks and improvements are recorded objectively.")),
    Manual("manual-08-path-planning", 8, "\u8def\u5f84\u89c4\u5212\u4eff\u771f", "Path-planning Simulation", "Day3_\u5b9e\u9a8c\u624b\u518c1-\u8def\u5f84\u89c4\u5212\u4eff\u771f.docx", "Run path-planning simulation experiments and compare route-generation behavior.", ("Simulation project files.", "Ubuntu environment with required dependencies.", "Terminal access in the project directory."), ("Prepare and build the simulation project as documented.", "Set start and goal conditions in the simulator or visualization tool.", "Run A*, RRT, RRT*, or the provided planning examples and observe outputs."), ("A route is generated for the selected task.", "The observed route can be compared across algorithms or parameters.", "Execution notes include commands, errors, and screenshots where applicable.")),
    Manual("manual-09-cflib", 9, "cflib \u5e93\u7f16\u7a0b", "cflib Programming", "Day3_\u5b9e\u9a8c\u624b\u518c2-cflib\u5e93\u7f16\u7a0b.docx", "Use cflib to structure Crazyflie connection, logging, parameter access, and command scripts.", ("Working Crazyflie connection.", "Python environment with cflib installed.", "Known radio URI or scanning procedure."), ("Initialize CRTP drivers and create a Crazyflie object.", "Use synchronized connection patterns for safer program structure.", "Read parameters or logs and send controlled commands."), ("The script connects and exits cleanly.", "Logged or printed values match the expected aircraft state.", "Motion commands are short, conservative, and explainable.")),
    Manual("manual-10-motion-commander", 10, "Motion Commander \u8fdb\u9636\u7f16\u7a0b", "Advanced Motion Commander Programming", "Day3_\u5b9e\u9a8c\u624b\u518c3-Motion Commander\u8fdb\u9636\u7f16\u7a0b.docx", "Use Motion Commander movement primitives to construct repeatable flight routines.", ("cflib script template.", "Safe test area.", "Instructor-approved height and speed parameters."), ("Create a MotionCommander context.", "Combine takeoff, landing, directional movement, turns, and pauses.", "Test short movement segments before a complete sequence."), ("The drone completes the intended primitive sequence.", "Timing, height, and distance choices are recorded.", "The program can be stopped safely if behavior deviates.")),
    Manual("manual-11-integrated-practice", 11, "\u9636\u6bb5\u7efc\u5408\u5b9e\u8df5", "Integrated Practice", "Day3_\u5b9e\u9a8c\u624b\u518c4-\u9636\u6bb5\u7efc\u5408\u5b9e\u8df5.docx", "Combine setup, sensing, planning, and control skills in a bounded practical task.", ("Completed prior manuals.", "Task area and constraints.", "Team role assignment for operation, monitoring, and recording."), ("Read the task constraints and define success criteria.", "Break the route or behavior into testable components.", "Run the integrated task and record results."), ("The task is completed within the defined constraints.", "The team can explain the selected method.", "Problems are documented with concrete evidence.")),
    Manual("manual-12-position-commander", 12, "PositionCommander", "PositionCommander", "Day3_\u5b9e\u9a8c\u624b\u518c5-PositionCommander.docx", "Use coordinate-based commands for waypoint routes and structured spatial tasks.", ("Crazyflie setup with appropriate positioning support.", "Coordinate-frame assumptions understood before flight.", "Waypoint list or route sketch."), ("Initialize PositionCommander or the documented position-control API.", "Set default height, speed, and coordinate frame carefully.", "Execute waypoint routes such as square, cube, star, or map-based paths."), ("The coordinate route matches the intended geometry.", "The aircraft remains inside the allowed volume.", "The route can be adjusted by editing explicit coordinates.")),
    Manual("manual-13-project-demo", 13, "\u7efc\u5408\u9879\u76ee\u5c55\u793a\u4efb\u52a1", "Integrated Project Demonstration", "Day3_\u5b9e\u9a8c\u624b\u518c6-\u7efc\u5408\u9879\u76ee\u5c55\u793a\u4efb\u52a1.docx", "Present a complete project task using the course experiments as technical basis.", ("Project objective and success criteria.", "Working code and tested hardware setup.", "Presentation evidence such as logs, route sketches, video, or screenshots."), ("Select a feasible demonstration task.", "Implement and rehearse the workflow under safety constraints.", "Present the method, result, limitations, and improvement plan."), ("The demonstration is executable or reproducible.", "The presentation explains method and evidence objectively.", "Safety, teamwork, and failure handling are included in the report.")),
]


def clean_output() -> None:
    for path in [ROOT / "zh", ROOT / "en", IMAGE_DIR, IMAGE_EN_DIR]:
        if path.exists():
            shutil.rmtree(path)
    (ROOT / "zh").mkdir(parents=True, exist_ok=True)
    (ROOT / "en").mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_EN_DIR.mkdir(parents=True, exist_ok=True)


def copy_final_test_images() -> None:
    for source, image_root in [
        (FINAL_TEST_ZH_SOURCE, IMAGE_DIR),
        (FINAL_TEST_EN_SOURCE, IMAGE_EN_DIR),
    ]:
        if not source.exists():
            raise FileNotFoundError(f"Missing final test image source: {source}")
        out_dir = image_root / FINAL_TEST_SLUG
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, out_dir / FINAL_TEST_IMAGE_NAME)


def relationship_map(zf: zipfile.ZipFile) -> dict[str, str]:
    rels_path = "word/_rels/document.xml.rels"
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    return {rel.attrib["Id"]: rel.attrib["Target"] for rel in root if "Id" in rel.attrib and "Target" in rel.attrib}


def text_from(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//w:t", NS)).strip()


def paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find("./w:pPr/w:pStyle", NS)
    return "" if style is None else style.attrib.get(f"{{{NS['w']}}}val", "")


def optimize_image_bytes(data: bytes, suffix: str) -> bytes:
    if Image is None or ImageOps is None:
        return data
    try:
        with Image.open(BytesIO(data)) as opened:
            if opened.width <= MAX_IMAGE_WIDTH and opened.height <= MAX_IMAGE_HEIGHT:
                return data
            image = ImageOps.exif_transpose(opened)
            image.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT), Image.Resampling.LANCZOS)
            output = BytesIO()
            if suffix in {".jpg", ".jpeg"}:
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                image.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
            elif suffix == ".webp":
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                image.save(output, format="WEBP", quality=88, method=6)
            else:
                if image.mode == "CMYK":
                    image = image.convert("RGB")
                image.save(output, format="PNG", optimize=True)
            optimized = output.getvalue()
            return optimized if len(optimized) < len(data) else data
    except Exception:
        return data


def copy_image(zf: zipfile.ZipFile, rels: dict[str, str], rid: str, manual: Manual, index: int) -> str | None:
    target = rels.get(rid)
    if not target:
        return None
    source_name = "word/" + target.lstrip("/")
    if source_name not in zf.namelist():
        return None
    out_dir = IMAGE_DIR / manual.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(source_name).suffix.lower() or ".png"
    out_path = out_dir / f"{index:03d}{suffix}"
    out_path.write_bytes(optimize_image_bytes(zf.read(source_name), suffix))
    return f"../assets/images/{manual.slug}/{out_path.name}"


def image_path_from_src(src: str) -> Path:
    return ROOT / src.removeprefix("../")


def image_src_from_en_path(path: Path) -> str:
    return "../" + path.relative_to(ROOT).as_posix()


def all_image_sources(extracted: dict[str, tuple[Manual, list[Block], dict[str, int]]]) -> set[str]:
    sources: set[str] = set()
    for _manual, blocks, _stats in extracted.values():
        for block in blocks:
            if isinstance(block, ParagraphBlock):
                sources.update(block.images)
    return sources


def load_image_ocr_cache() -> dict[str, list[dict[str, object]]]:
    if not IMAGE_OCR_CACHE.exists():
        return {}
    return json.loads(IMAGE_OCR_CACHE.read_text(encoding="utf-8"))


def save_image_ocr_cache(cache: dict[str, list[dict[str, object]]]) -> None:
    IMAGE_OCR_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def image_digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


_OCR_ENGINE = None
_OCR_UNAVAILABLE = False


def get_ocr_engine():
    global _OCR_ENGINE, _OCR_UNAVAILABLE
    if _OCR_UNAVAILABLE:
        return None
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        _OCR_UNAVAILABLE = True
        print("rapidocr-onnxruntime is not installed; English image text replacement skipped.")
        return None
    _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def ocr_image(path: Path, cache: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    if Image is None:
        return []
    digest = image_digest(path)
    if digest in cache:
        return cache[digest]
    engine = get_ocr_engine()
    if engine is None:
        cache[digest] = []
        return []
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        width, height = image.size
        scale = min(1.0, OCR_MAX_IMAGE_SIDE / max(width, height))
        if scale < 1.0:
            image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
        try:
            import numpy as np
            result, _elapsed = engine(np.array(image))
        except Exception:
            result, _elapsed = engine(str(path))
            scale = 1.0
    items: list[dict[str, object]] = []
    for box, text, score in result or []:
        if score < 0.5 or not has_cjk(text):
            continue
        mapped_box = [[float(x) / scale, float(y) / scale] for x, y in box]
        items.append({"box": mapped_box, "text": text.strip(), "score": float(score)})
    cache[digest] = items
    return items


def collect_image_ocr(extracted: dict[str, tuple[Manual, list[Block], dict[str, int]]]) -> dict[str, list[dict[str, object]]]:
    cache = load_image_ocr_cache()
    image_ocr: dict[str, list[dict[str, object]]] = {}
    sources = sorted(all_image_sources(extracted))
    for index, src in enumerate(sources, 1):
        path = image_path_from_src(src)
        items = ocr_image(path, cache)
        if items:
            image_ocr[src] = items
        save_image_ocr_cache(cache)
        if os.environ.get("VERBOSE_OCR") or index % 20 == 0 or index == len(sources):
            print(f"OCR checked {index}/{len(sources)} images...", flush=True)
    save_image_ocr_cache(cache)
    print(f"OCR found Chinese text in {len(image_ocr)} images.")
    return image_ocr


def collect_image_translation_texts(image_ocr: dict[str, list[dict[str, object]]]) -> set[str]:
    return {str(item["text"]).strip() for items in image_ocr.values() for item in items if str(item["text"]).strip()}


def dominant_color(image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    rgb.thumbnail((80, 80))
    pixels = list(rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata())
    if not pixels:
        return (255, 255, 255)
    quantized = Counter((r // 16 * 16, g // 16 * 16, b // 16 * 16) for r, g, b in pixels)
    r, g, b = quantized.most_common(1)[0][0]
    return (min(255, r + 8), min(255, g + 8), min(255, b + 8))


def average_luminance(image) -> float:
    rgb = image.convert("RGB")
    rgb.thumbnail((80, 80))
    pixels = list(rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata())
    if not pixels:
        return 255
    return sum(luminance(pixel) for pixel in pixels) / len(pixels)


def luminance(color: tuple[int, int, int]) -> float:
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def english_font(size: int):
    if ImageFont is None:
        return None
    for font_path in [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def text_bbox(draw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_translation(text: str, draw, font, max_width: int) -> list[str]:
    words = re.split(r"\s+", text.strip())
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or text_bbox(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [text]


def clean_image_translation(text: str) -> str:
    cleaned = re.sub(r"�+", "", text)
    cleaned = cleaned.replace("○", "").replace("●", "").replace("（", "(").replace("）", ")")
    cleaned = cleaned.replace("<Previous step", "Back").replace("Previous step", "Back")
    cleaned = cleaned.replace("Next(N)>", "Next").replace("Next (N)>", "Next").replace("Next step", "Next")
    cleaned = cleaned.replace("help", "Help")
    cleaned = cleaned.replace("Please enter the number in your mouth to select", "Please enter the number at the prompt to select")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 180:
        cleaned = cleaned[:177].rstrip() + "..."
    return cleaned or "English"


def draw_translated_text(image, item: dict[str, object], cache: dict[str, str]) -> None:
    if ImageDraw is None:
        return
    source = str(item["text"]).strip()
    translated = clean_image_translation(cache.get(source, source))
    box = item["box"]
    xs = [point[0] for point in box]  # type: ignore[index]
    ys = [point[1] for point in box]  # type: ignore[index]
    x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    height = max(8, y2 - y1)
    width = max(12, x2 - x1)
    pad = max(2, int(height * 0.16))
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(image.width - 1, x2 + pad)
    y2 = min(image.height - 1, y2 + pad)
    if height < 28 and width < 150:
        target_w = min(image.width - x1 - 2, max(width + pad * 2, min(width + 44, image.width - x1 - 2)))
        target_h = min(image.height - y1 - 2, max(height + pad * 2, 22))
    else:
        grow = 1.35 if len(translated) <= max(12, len(source) * 2) else 2.25
        target_w = min(image.width - x1 - 2, max(width, int(width * grow), min(width + 180, image.width - x1 - 2)))
        target_h = min(image.height - y1 - 2, max(height, int(height * 2.2)))
    x2 = min(image.width - 1, x1 + target_w)
    y2 = min(image.height - 1, y1 + target_h)
    draw = ImageDraw.Draw(image)
    bg = dominant_color(image.crop((x1, y1, max(x2, x1 + 1), max(y2, y1 + 1))))
    fg = (0, 0, 0) if luminance(bg) > 145 else (255, 255, 255)
    max_width = max(10, x2 - x1 - 6)
    max_height = max(8, y2 - y1 - 4)
    size = min(24, max(7, int(height * 0.82)))
    lines: list[str] = [translated]
    line_height = size + 2
    while size >= 6:
        font = english_font(size)
        lines = wrap_translation(translated, draw, font, max_width)
        line_height = text_bbox(draw, "Ag", font)[1] + 3
        if line_height * len(lines) <= max_height:
            break
        size -= 1
    font = english_font(size)
    line_height = text_bbox(draw, "Ag", font)[1] + 3
    draw.rectangle((x1, y1, x2, y2), fill=bg)
    yy = y1 + 2
    for line in lines[: max(1, max_height // max(1, line_height))]:
        draw.text((x1 + 3, yy), line, fill=fg, font=font)
        yy += line_height


def should_use_translation_panel(image, items: list[dict[str, object]]) -> bool:
    if not items:
        return False
    dark_dense_terminal = average_luminance(image) < 95 and len(items) >= 4
    wide_dense_ui = image.width > image.height * 1.35 and len(items) >= 18
    very_dense = len(items) >= 28
    return dark_dense_terminal or wide_dense_ui or very_dense


def draw_translation_panel(image, items: list[dict[str, object]], cache: dict[str, str]) -> None:
    if ImageDraw is None:
        return
    bg = dominant_color(image)
    if average_luminance(image) < 95:
        bg = (48, 5, 31)
    else:
        bg = (250, 250, 250)
    fg = (255, 255, 255) if luminance(bg) < 145 else (28, 28, 28)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, image.height), fill=bg)
    ordered = sorted(items, key=lambda item: (min(point[1] for point in item["box"]), min(point[0] for point in item["box"])))  # type: ignore[index]
    lines: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        source = str(item["text"]).strip()
        translated = clean_image_translation(cache.get(source, source))
        if translated.lower() in seen:
            continue
        seen.add(translated.lower())
        lines.append(translated)
    margin = max(14, image.width // 60)
    font_size = max(11, min(22, image.width // 64))
    font = english_font(font_size)
    columns = 2 if image.width > 1000 and len(lines) > 18 else 1
    column_gap = margin * 2 if columns > 1 else 0
    max_width = (image.width - margin * 2 - column_gap) // columns
    wrapped: list[str] = []
    line_groups = [wrap_translation(line, draw, font, max_width) for line in lines]
    wrapped = [line for group in line_groups for line in group]
    while font_size > 8:
        font = english_font(font_size)
        line_height = text_bbox(draw, "Ag", font)[1] + 5
        lines_per_column = max(1, (image.height - margin * 2) // line_height)
        if len(wrapped) <= lines_per_column * columns:
            break
        font_size -= 1
        font = english_font(font_size)
        line_groups = [wrap_translation(line, draw, font, max_width) for line in lines]
        wrapped = [line for group in line_groups for line in group]
    line_height = text_bbox(draw, "Ag", font)[1] + 5
    lines_per_column = max(1, (image.height - margin * 2) // line_height)
    for index, line in enumerate(wrapped[: lines_per_column * columns]):
        column = index // lines_per_column
        row = index % lines_per_column
        x = margin + column * (max_width + column_gap)
        y = margin + row * line_height
        draw.text((x, y), line, fill=fg, font=font)


def build_english_images(image_ocr: dict[str, list[dict[str, object]]], cache: dict[str, str]) -> dict[str, str]:
    if Image is None:
        return {}
    image_map: dict[str, str] = {}
    for src, items in sorted(image_ocr.items()):
        source_path = image_path_from_src(src)
        relative = source_path.relative_to(IMAGE_DIR)
        out_path = IMAGE_EN_DIR / relative
        curated_path = IMAGE_EN_CURATED_DIR / relative
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if curated_path.exists():
            shutil.copyfile(curated_path, out_path)
            image_map[src] = image_src_from_en_path(out_path)
            continue
        with Image.open(source_path) as opened:
            image = opened.convert("RGB")
        if should_use_translation_panel(image, items):
            draw_translation_panel(image, items, cache)
        else:
            for item in items:
                draw_translated_text(image, item, cache)
        suffix = out_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            image.save(out_path, format="JPEG", quality=90, optimize=True, progressive=True)
        else:
            image.save(out_path, format="PNG", optimize=True)
        image_map[src] = image_src_from_en_path(out_path)
    return image_map


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def is_code_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith(("http://", "https://")):
        return True
    if re.match(r"^(sudo|pip|python|python3|ros|rosrun|roslaunch|catkin|source|git|cd|mkdir|touch|ping|reboot)\b", stripped):
        return True
    if re.match(r"^(import\b|from\b|def\b|class\b|if __name__|for |while |with |try:|except|return\b|print\(|#)", stripped):
        return True
    return False


def is_code_style(style: str) -> bool:
    return style.strip().lower() in {"html", "code", "sourcecode", "source code"}


def is_code_block(block: Block) -> bool:
    return (
        isinstance(block, ParagraphBlock)
        and bool(block.text.strip())
        and not block.images
        and (is_code_style(block.style) or is_code_like(block.text))
    )


def load_translation_cache() -> dict[str, str]:
    if not TRANSLATION_CACHE.exists():
        return {}
    return json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))


def save_translation_cache(cache: dict[str, str]) -> None:
    TRANSLATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def translation_opener() -> urllib.request.OpenerDirector:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "http://127.0.0.1:7888"
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def translate_remote(text: str, opener: urllib.request.OpenerDirector) -> str:
    query = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=zh-CN&tl=en&dt=t&q={query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            with opener.open(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
            data = json.loads(payload)
            translated = "".join(part[0] for part in data[0] if part and part[0])
            return translated.strip() or text
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            if attempt == 3:
                return text
            time.sleep(1.5 * (attempt + 1))
    return text


def should_translate(text: str) -> bool:
    stripped = text.strip()
    if not stripped or not has_cjk(stripped):
        return False
    if is_code_like(stripped):
        return stripped.startswith("#") or "#" in stripped
    return True


def ensure_translations(texts: set[str]) -> dict[str, str]:
    cache = load_translation_cache()
    pending = sorted(text for text in texts if should_translate(text) and text not in cache)
    if not pending:
        return cache

    opener = translation_opener()
    completed = 0
    print(f"Translating {len(pending)} text blocks for English pages...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(translate_remote, text, opener): text for text in pending}
        for future in as_completed(futures):
            source = futures[future]
            cache[source] = future.result()
            completed += 1
            if completed % 50 == 0 or completed == len(pending):
                save_translation_cache(cache)
                print(f"Translated {completed}/{len(pending)}")
    return cache


def english_text(text: str, cache: dict[str, str]) -> str:
    if not should_translate(text):
        return text
    return cache.get(text, text)


def is_source_manual_heading(text: str) -> bool:
    return re.match(r"^实验手册\s*\d+\s*[—–-]+", text.strip()) is not None


SECTION_HEADINGS = {
    "实验目标": ("一、实验目标", "1. Experimental goals"),
    "实验准备": ("二、实验准备", "2. Experimental preparation"),
    "实验步骤": ("三、实验步骤", "3. Experimental steps"),
    "实验验证与测试": ("四、实验验证与测试", "4. Experimental verification and testing"),
    "实验总结与拓展": ("五、实验总结与拓展", "5. Experiment summary and extension"),
    "链接资料整理": ("链接资料整理", "Reference links"),
}


CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


STANDALONE_H2 = {
    "实验内容",
    "复习",
    "创意板块",
    "竞速板块",
    "最终综合展示评价说明",
}


TOP_LEVEL_NUMBERED_H2 = {
    "阶段综合实践说明",
    "实践任务",
    "综合项目展示任务说明",
    "任务内容",
}


GOAL_ITEM_PREFIXES = (
    "理解",
    "掌握",
    "编写",
    "学习",
    "熟悉",
    "成功",
    "通过",
    "能够",
    "继续",
    "使用",
)


STANDALONE_H3 = {
    "硬件要求",
    "软件资源（可从官网下载，为节省时间由助教拷贝）",
    "工具准备",
    "下载与安装",
    "验证安装",
    "新建虚拟机向导",
    "命名与存储",
    "硬件配置",
    "加载ISO镜像",
    "启动虚拟机",
    "系统安装流程",
    "系统初始化",
    "安装VMware Tools",
    "网络连通性测试",
    "快照恢复测试",
    "核心知识点回顾",
    "拓展任务（选做）",
    "如何读懂LED灯的含义",
    "程序执行流程",
    "核心部件",
    "起飞功能",
    "前进、转弯和后退",
    "记录飞行数据",
    "来回游荡",
    "重要注意事项！！！",
    "代码范例",
    "关键参数",
    "参数详解",
    "提示",
    "两种方式",
}


HEADING_TRANSLATIONS = {
    "阶段综合实践说明": "Stage integrated practice instructions",
    "实践任务": "Practice tasks",
    "综合项目展示任务说明": "Integrated project demonstration task description",
    "任务内容": "Task content",
    "创意板块": "Creative task section",
    "竞速板块": "Speed task section",
    "题目说明": "Task description",
    "展示流程": "Demonstration procedure",
    "评价标准细则": "Detailed evaluation criteria",
    "展示评价说明": "Demonstration evaluation instructions",
    "展示建议": "Demonstration suggestions",
    "最终综合展示评价说明": "Final integrated demonstration evaluation",
    "实验内容": "Experiment content",
    "复习": "Review",
    "程序执行流程": "Program execution flow",
    "核心部件": "Core components",
    "重要注意事项！！！": "Important notes",
    "代码范例": "Code example",
    "关键参数": "Key parameters",
    "参数详解": "Parameter details",
    "提示": "Tip",
    "两种方式": "Two methods",
    "花样飞行": "Pattern flight",
    "巡航飞行": "Cruise flight",
}


def normalized_section_heading(text: str) -> str | None:
    stripped = text.strip().rstrip(":：")
    stripped = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", stripped)
    stripped = re.sub(r"^\d+[.)、.．]\s*", "", stripped)
    return stripped if stripped in SECTION_HEADINGS else None


def chinese_number_to_int(text: str) -> int | None:
    if not text:
        return None
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CHINESE_DIGITS.get(left, 1) if left else 1
        ones = CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return CHINESE_DIGITS.get(text)


def heading_translation(source: str, cache: dict[str, str]) -> str:
    return HEADING_TRANSLATIONS.get(source, english_text(source, cache))


def is_reference_line(text: str) -> bool:
    return any(marker in text for marker in ("网页标题", "课堂用途", "原始链接", "http://", "https://"))


def is_numbered_subheading(body: str, original: str) -> bool:
    if is_reference_line(body) or len(body) > 55:
        return False
    if body.startswith(GOAL_ITEM_PREFIXES):
        return False
    if re.match(r"^\d+[.)、.．]\S", original):
        return len(body) <= 28 or any(word in body for word in ("题目", "展示", "评价", "建议", "算法", "初始化", "坐标", "移动"))
    if original.rstrip().endswith((":", "：")):
        return True
    return any(word in body for word in ("题目", "展示", "评价", "建议", "算法", "初始化", "坐标", "移动"))


def structural_heading(text: str, style: str = "") -> HeadingInfo | None:
    stripped = text.strip()
    if not stripped or is_source_manual_heading(stripped) or is_code_like(stripped):
        return None

    section_heading = normalized_section_heading(stripped)
    if section_heading:
        zh, en = SECTION_HEADINGS[section_heading]
        return HeadingInfo(level=2, zh_text=zh, en_text=en)

    compact = stripped.rstrip(":：").strip()
    if compact in STANDALONE_H2:
        return HeadingInfo(level=2, zh_text=compact, en_source=compact)
    if compact in STANDALONE_H3:
        return HeadingInfo(level=3, zh_text=compact, en_source=compact)

    match = re.match(r"^([一二三四五六七八九十]+)[、.．]\s*(.+)$", compact)
    if match:
        number_text, body = match.groups()
        number = chinese_number_to_int(number_text)
        if number is not None and len(body) <= 55 and not is_reference_line(body):
            level = 2 if body in TOP_LEVEL_NUMBERED_H2 else 3
            return HeadingInfo(level=level, zh_text=f"{number_text}、{body}", en_source=body, en_prefix=f"{number}. ")

    match = re.match(r"^实验([一二三四五六七八九十]+)(（[^）]+）)?[：:]\s*(.+)$", stripped)
    if match:
        number_text, qualifier, body = match.groups()
        number = chinese_number_to_int(number_text)
        if number is not None:
            en_suffix = " (optional extension)" if qualifier and ("拓展" in qualifier or "选做" in qualifier) else ""
            return HeadingInfo(level=3, zh_text=f"实验{number_text}{qualifier or ''}：{body}", en_source=body, en_prefix=f"Experiment {number}{en_suffix}: ")

    match = re.match(r"^实验[：:]\s*(.+)$", stripped)
    if match:
        body = match.group(1).strip()
        return HeadingInfo(level=3, zh_text=f"实验：{body}", en_source=body, en_prefix="Experiment: ")

    match = re.match(r"^题目([一二三四五六七八九十]+)[：:]\s*(.+)$", stripped)
    if match:
        number_text, body = match.groups()
        number = chinese_number_to_int(number_text)
        if number is not None:
            return HeadingInfo(level=3, zh_text=f"题目{number_text}：{body}", en_source=body, en_prefix=f"Task {number}: ")

    match = re.match(r"^阶段(\d+)[：:]\s*(.+)$", stripped)
    if match:
        number, body = match.groups()
        return HeadingInfo(level=3, zh_text=f"阶段{number}：{body}", en_source=body, en_prefix=f"Stage {number}: ")

    match = re.match(r"^(\d+)[.)、.．]\s*(.+)$", compact)
    if match:
        number, body = match.groups()
        if is_numbered_subheading(body, stripped):
            return HeadingInfo(level=3, zh_text=f"{number}. {body}", en_source=body, en_prefix=f"{number}. ")

    if style.lower().startswith("heading"):
        return HeadingInfo(level=3, zh_text=stripped, en_source=stripped)
    return None


def render_heading(heading: HeadingInfo, lang: str, cache: dict[str, str]) -> str:
    if lang == "zh":
        return heading.zh_text
    if heading.en_text is not None:
        return heading.en_text
    source = heading.en_source or heading.zh_text
    return f"{heading.en_prefix}{heading_translation(source, cache)}{heading.en_suffix}".strip()


def bullet_item_text(text: str) -> str | None:
    match = re.match(r"^\s*[*•]\s+(.+)$", text.strip())
    return match.group(1).strip() if match else None


def numbered_item_parts(text: str) -> tuple[int, str] | None:
    match = re.match(r"^\s*(\d+)[.)、.．]\s*(.+)$", text.strip())
    return (int(match.group(1)), match.group(2).strip()) if match else None


def render_paragraph(text: str, style: str, images: tuple[str, ...], lang: str, cache: dict[str, str], image_map: dict[str, str] | None = None) -> str:
    stripped = text.strip()
    blocks: list[str] = []
    if stripped and not is_source_manual_heading(stripped):
        heading = structural_heading(stripped, style)
        if heading:
            rendered = render_heading(heading, lang, cache)
        else:
            rendered = english_text(stripped, cache) if lang == "en" else stripped
        escaped = html.escape(rendered)
        if heading:
            blocks.append(f"<h{heading.level}>{escaped}</h{heading.level}>")
        elif is_code_like(stripped):
            blocks.append(f"<pre><code>{escaped}</code></pre>")
        elif re.match(r"^[0-9]+[.)]\s", stripped):
            blocks.append(f'<p class="step">{escaped}</p>')
        else:
            blocks.append(f"<p>{escaped}</p>")
    for src in images:
        display_src = image_map.get(src, src) if lang == "en" and image_map else src
        alt = english_text(stripped[:80], cache) if lang == "en" else stripped[:80]
        blocks.append(f'<figure><img src="{html.escape(display_src)}" alt="{html.escape(alt or "manual image")}" loading="lazy" decoding="async"></figure>')
    return "\n".join(blocks)


def table_to_rows(table: ET.Element) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for tr in table.findall("./w:tr", NS):
        cells = tuple(text_from(tc) for tc in tr.findall("./w:tc", NS))
        if cells:
            rows.append(cells)
    return tuple(rows)


def render_table(rows: tuple[tuple[str, ...], ...], lang: str, cache: dict[str, str]) -> str:
    rendered_rows = []
    for row in rows:
        cells = []
        for cell in row:
            text = english_text(cell, cache) if lang == "en" else cell
            cells.append(f"<td>{html.escape(text)}</td>")
        rendered_rows.append("<tr>" + "".join(cells) + "</tr>")
    return "" if not rendered_rows else "<table><tbody>\n" + "\n".join(rendered_rows) + "\n</tbody></table>"


def extract_manual(manual: Manual) -> tuple[list[Block], dict[str, int]]:
    source = SOURCE_DIR / manual.source_name
    if not source.exists():
        raise FileNotFoundError(source)
    blocks: list[Block] = []
    stats = {"paragraphs": 0, "tables": 0, "images": 0}
    with zipfile.ZipFile(source) as zf:
        rels = relationship_map(zf)
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find("w:body", NS)
        if body is None:
            return blocks, stats
        image_index = 0
        for child in body:
            if child.tag == f"{{{NS['w']}}}p":
                text = text_from(child)
                images: list[str] = []
                for blip in child.findall(".//a:blip", NS):
                    rid = blip.attrib.get(f"{{{NS['r']}}}embed")
                    if rid:
                        image_index += 1
                        src = copy_image(zf, rels, rid, manual, image_index)
                        if src:
                            images.append(src)
                            stats["images"] += 1
                if text or images:
                    stats["paragraphs"] += 1
                    blocks.append(ParagraphBlock(text, paragraph_style(child), tuple(images)))
            elif child.tag == f"{{{NS['w']}}}tbl":
                table = table_to_rows(child)
                if table:
                    stats["tables"] += 1
                    blocks.append(TableBlock(table))
    return blocks, stats


def collect_translation_texts(blocks: list[Block]) -> set[str]:
    texts: set[str] = set()
    for block in blocks:
        if isinstance(block, ParagraphBlock):
            if is_code_block(block):
                continue
            heading = structural_heading(block.text, block.style)
            if heading:
                if heading.en_source and heading.en_source not in HEADING_TRANSLATIONS and should_translate(heading.en_source):
                    texts.add(heading.en_source.strip())
                if block.images and should_translate(block.text[:80]):
                    texts.add(block.text[:80].strip())
                continue
            bullet_text = bullet_item_text(block.text)
            if bullet_text and should_translate(bullet_text):
                texts.add(bullet_text.strip())
                continue
            numbered_item = numbered_item_parts(block.text)
            if numbered_item and not structural_heading(block.text, block.style) and should_translate(numbered_item[1]):
                texts.add(numbered_item[1].strip())
                continue
            if should_translate(block.text):
                texts.add(block.text.strip())
            if block.images and should_translate(block.text[:80]):
                texts.add(block.text[:80].strip())
        else:
            for row in block.rows:
                for cell in row:
                    if should_translate(cell):
                        texts.add(cell.strip())
    return texts


def render_blocks(blocks: list[Block], lang: str, cache: dict[str, str], image_map: dict[str, str] | None = None) -> str:
    rendered: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if is_code_block(block):
            code_lines: list[str] = []
            while index < len(blocks) and is_code_block(blocks[index]):
                code_lines.append(blocks[index].text.strip())  # type: ignore[union-attr]
                index += 1
            rendered.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue
        if isinstance(block, ParagraphBlock) and bullet_item_text(block.text) and not block.images:
            items: list[str] = []
            while index < len(blocks):
                current = blocks[index]
                if not isinstance(current, ParagraphBlock) or current.images:
                    break
                item_text = bullet_item_text(current.text)
                if not item_text:
                    break
                item = english_text(item_text, cache) if lang == "en" else item_text
                items.append(f"<li>{html.escape(item)}</li>")
                index += 1
            rendered.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue
        numbered_item = numbered_item_parts(block.text) if isinstance(block, ParagraphBlock) else None
        if isinstance(block, ParagraphBlock) and numbered_item and not block.images and not structural_heading(block.text, block.style):
            items: list[str] = []
            start_number = numbered_item[0]
            while index < len(blocks):
                current = blocks[index]
                if not isinstance(current, ParagraphBlock) or current.images or structural_heading(current.text, current.style):
                    break
                item_parts = numbered_item_parts(current.text)
                if not item_parts:
                    break
                _, item_text = item_parts
                item = english_text(item_text, cache) if lang == "en" else item_text
                items.append(f"<li>{html.escape(item)}</li>")
                index += 1
            rendered.append(f'<ol class="numbered-list" start="{start_number}">\n' + "\n".join(items) + "\n</ol>")
            continue
        if isinstance(block, ParagraphBlock):
            html_block = render_paragraph(block.text, block.style, block.images, lang, cache, image_map)
        else:
            html_block = render_table(block.rows, lang, cache)
        if html_block:
            rendered.append(html_block)
        index += 1
    return "\n".join(rendered)


def nav_html(lang: str, current_slug: str | None = None) -> str:
    home = "\u9996\u9875" if lang == "zh" else "Home"
    items = [f'<li><a class="{"active" if current_slug is None else ""}" href="index.html">{home}</a></li>']
    for manual in MANUALS:
        title = manual.zh_title if lang == "zh" else manual.en_title
        label = f"\u5b9e\u9a8c {manual.number}" if lang == "zh" else f"Experiment {manual.number}"
        active = " active" if current_slug == manual.slug else ""
        items.append(f'<li><a class="{active.strip()}" href="{manual.slug}.html"><span>{label}</span>{html.escape(title)}</a></li>')
    return "\n".join(items)


def layout(lang: str, title: str, body: str, current_slug: str | None = None) -> str:
    zh_href = "index.html" if lang == "zh" else f"../zh/{'index.html' if current_slug is None else current_slug + '.html'}"
    en_href = "index.html" if lang == "en" else f"../en/{'index.html' if current_slug is None else current_slug + '.html'}"
    language_switch = (
        f'<span>\u4e2d\u6587</span><a href="{en_href}">English</a>'
        if lang == "zh"
        else f'<a href="{zh_href}">\u4e2d\u6587</a><span>English</span>'
    )
    project_title = "\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u624b\u518c" if lang == "zh" else "Palm-sized UAV Experiment Manual"
    search = "\u641c\u7d22\u6587\u6863" if lang == "zh" else "Search docs"
    caption = "\u76ee\u5f55" if lang == "zh" else "Contents"
    github = "\u5728 GitHub \u4e0a\u67e5\u770b" if lang == "zh" else "View on GitHub"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - {html.escape(project_title)}</title>
  <link rel="stylesheet" href="../assets/style.css">
</head>
<body>
  <aside class="wy-nav-side">
    <div class="wy-side-scroll">
      <div class="wy-side-nav-search">
        <a class="icon-home" href="index.html">{html.escape(project_title)}</a>
        <div class="version">latest</div>
        <input id="doc-search" type="search" placeholder="{search}" aria-label="{search}">
      </div>
      <nav class="wy-menu">
        <p class="caption">{caption}</p>
        <ul id="nav-list">{nav_html(lang, current_slug)}</ul>
      </nav>
    </div>
  </aside>
  <main class="wy-nav-content-wrap">
    <div class="mobile-bar"><button id="menu-toggle" aria-label="Toggle navigation">&#9776;</button><span>{html.escape(project_title)}</span></div>
    <article class="wy-nav-content">
      <div class="rst-content">
        <div class="breadcrumbs"><a href="index.html">Docs</a><span>&rsaquo;</span><span>{html.escape(title)}</span><a class="github-link" href="https://github.com/Admire-ljb/summer-school-experiment-manual">{github}</a></div>
        <div class="language-switch">{language_switch}</div>
        {body}
      </div>
    </article>
  </main>
  <script src="../assets/site.js"></script>
</body>
</html>
"""


def write_index(lang: str) -> None:
    if lang == "zh":
        body = (
            "<h1>\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u624b\u518c</h1>"
            "<p>\u672c\u624b\u518c\u9762\u5411\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u8bfe\u7a0b\uff0c\u5185\u5bb9\u5305\u62ec\u73af\u5883\u914d\u7f6e\u3001\u4f20\u611f\u5668\u4f7f\u7528\u3001\u8def\u5f84\u89c4\u5212\u3001cflib \u7f16\u7a0b\u548c\u7efc\u5408\u9879\u76ee\u4efb\u52a1\u3002</p>"
            "<div class=\"admonition warning\"><p class=\"admonition-title\">\u5b89\u5168\u8bf4\u660e</p>"
            "<p>\u6d89\u53ca\u771f\u5b9e\u98de\u884c\u7684\u5b9e\u9a8c\u5fc5\u987b\u5728\u6559\u5e08\u6216\u52a9\u6559\u786e\u8ba4\u573a\u5730\u3001\u8bbe\u5907\u3001\u7535\u6c60\u548c\u6025\u505c\u6d41\u7a0b\u540e\u8fdb\u884c\u3002</p></div>"
            "<h2>\u5b9e\u9a8c\u76ee\u5f55</h2><div class=\"toctree-wrapper\">"
        )
        for manual in MANUALS:
            body += f'<a class="doc-card" href="{manual.slug}.html"><span>\u5b9e\u9a8c {manual.number}</span><strong>{html.escape(manual.zh_title)}</strong><em>{html.escape(manual.en_title)}</em></a>\n'
        body += "</div>"
        title = "\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u624b\u518c"
    else:
        body = "<h1>Palm-sized UAV Experiment Manual</h1><p>This manual covers environment setup, sensor use, path-planning simulation, cflib programming, flight-control routines, and integrated project tasks for palm-sized UAV experiments.</p><div class=\"admonition warning\"><p class=\"admonition-title\">Safety note</p><p>Experiments involving real flight must be conducted only after the instructor or teaching assistant confirms the arena, equipment, batteries, and emergency-stop procedure.</p></div><h2>Experiment list</h2><div class=\"toctree-wrapper\">"
        for manual in MANUALS:
            body += f'<a class="doc-card" href="{manual.slug}.html"><span>Experiment {manual.number}</span><strong>{html.escape(manual.en_title)}</strong></a>\n'
        body += "</div>"
        title = "Palm-sized UAV Experiment Manual"
    (ROOT / lang / "index.html").write_text(layout(lang, title, body), encoding="utf-8")

def english_body(manual: Manual, blocks: list[Block], cache: dict[str, str], image_map: dict[str, str]) -> str:
    return f"""
<h1>Experiment {manual.number}: {html.escape(manual.en_title)}</h1>
{render_blocks(blocks, "en", cache, image_map)}
"""


def final_test_image_src(lang: str) -> str:
    image_root = "images-en" if lang == "en" else "images"
    return f"../assets/{image_root}/{FINAL_TEST_SLUG}/{FINAL_TEST_IMAGE_NAME}"


def final_project_demo_body(manual: Manual, lang: str) -> str:
    if lang == "zh":
        image_src = final_test_image_src("zh")
        return f"""
<h1>实验 {manual.number}: {html.escape(manual.zh_title)}</h1>
<p class="subtitle">{html.escape(manual.en_title)}</p>
<h2>最后综合测试</h2>
<p>本实验最终评价仅设置一项综合测试任务。无人机以 0.3 m/s 的固定速度飞行，从 A 区域内任意位置起飞，飞行过程中需要经过 B 点和 C 点，经过 B、C 的顺序不限，最终降落回 A 区域内。</p>
<figure class="wide-figure"><img src="{html.escape(image_src)}" alt="最后综合测试地图与评分规则" loading="lazy" decoding="async"></figure>
<h3>场地约束</h3>
<ul>
<li>挡板位置不一定固定，教师可根据测试批次调整挡板布置，现场以实际摆放为准。</li>
<li>奖励点和起止点是固定的：R1、R2、R3、R4 的位置固定；起止区域固定为 A 区域。</li>
<li>程序不应只硬编码图中挡板坐标，应结合传感器数据、现场观测或规划策略完成避障与路径调整。</li>
</ul>
<h3>评分规则</h3>
<ul>
<li>最终成绩：S = v &times; t - Reward + Punish，成绩值越小越优。</li>
<li>Reward：R1、R2、R3 的奖励值均为 2 m，R4 的奖励值为 5 m。</li>
<li>Punish：最终降落在 A 区时位置不规范，惩罚 0.35 m；未经过 B 点或 C 点，单点惩罚 10 m；最终未回归 A 区，惩罚 20 m。</li>
<li>可使用传感器包括光流测速测高模块和水平测距传感器。</li>
</ul>
<h3>展示要求</h3>
<ul>
<li>展示前应向教师说明代码逻辑、速度设置、传感器使用方式和急停方案。</li>
<li>飞行过程中需保持一名同学负责终端控制和急停，另一名同学记录完整飞行过程。</li>
<li>若无人机接触挡板、姿态明显异常或进入不安全状态，应立即终止程序。</li>
</ul>
"""
    image_src = final_test_image_src("en")
    return f"""
<h1>Experiment {manual.number}: {html.escape(manual.en_title)}</h1>
<h2>Final Comprehensive Test</h2>
<p>The final assessment contains one comprehensive task only. The drone flies at a constant speed of 0.3 m/s, takes off from any position inside Area A, passes through points B and C in any order, and finally lands back inside Area A.</p>
<figure class="wide-figure"><img src="{html.escape(image_src)}" alt="Final comprehensive test map and scoring rules" loading="lazy" decoding="async"></figure>
<h3>Arena Constraints</h3>
<ul>
<li>Baffle positions are not necessarily fixed; the instructor may adjust the baffle layout between test runs, and the on-site setup is authoritative.</li>
<li>The reward points and start/end points are fixed: R1, R2, R3, and R4 keep their positions, and the start/end area is fixed as Area A.</li>
<li>The program should not only hard-code the baffle coordinates shown in the diagram. It should use sensor data, on-site observation, or planning logic to avoid obstacles and adjust the route.</li>
</ul>
<h3>Scoring Rules</h3>
<ul>
<li>Final score: S = v &times; t - Reward + Punish. A lower score is better.</li>
<li>Reward: R1, R2, and R3 are worth 2 m each; R4 is worth 5 m.</li>
<li>Punish: a non-standard final landing in Area A adds 0.35 m; missing point B or C adds 10 m per point; failing to return to Area A adds 20 m.</li>
<li>Available sensors include the Flow deck for velocity and height measurement and the horizontal range sensor.</li>
</ul>
<h3>Demonstration Requirements</h3>
<ul>
<li>Before the demonstration, explain the code logic, speed setting, sensor usage, and emergency-stop plan to the instructor.</li>
<li>During flight, one student should monitor the terminal and emergency stop, while another student records the full flight process.</li>
<li>If the drone touches a baffle, shows abnormal attitude, or enters an unsafe state, stop the program immediately.</li>
</ul>
"""


def write_pages() -> dict[str, dict[str, int]]:
    manifest: dict[str, dict[str, int]] = {}
    extracted: dict[str, tuple[Manual, list[Block], dict[str, int]]] = {}
    translation_texts: set[str] = set()
    for manual in MANUALS:
        blocks, stats = extract_manual(manual)
        extracted[manual.slug] = (manual, blocks, stats)
        manifest[manual.slug] = stats
        translation_texts.update(collect_translation_texts(blocks))

    image_ocr = collect_image_ocr(extracted)
    translation_texts.update(collect_image_translation_texts(image_ocr))
    cache = ensure_translations(translation_texts)
    image_map = build_english_images(image_ocr, cache)
    copy_final_test_images()

    for manual, blocks, _stats in extracted.values():
        if manual.slug == FINAL_TEST_SLUG:
            zh_body = final_project_demo_body(manual, "zh")
            en_body = final_project_demo_body(manual, "en")
        else:
            zh_body = f'<h1>\u5b9e\u9a8c {manual.number}: {html.escape(manual.zh_title)}</h1><p class="subtitle">{html.escape(manual.en_title)}</p>' + render_blocks(blocks, "zh", cache)
            en_body = english_body(manual, blocks, cache, image_map)
        (ROOT / "zh" / f"{manual.slug}.html").write_text(layout("zh", manual.zh_title, zh_body, manual.slug), encoding="utf-8")
        (ROOT / "en" / f"{manual.slug}.html").write_text(layout("en", manual.en_title, en_body, manual.slug), encoding="utf-8")
    return manifest


def write_assets() -> None:
    (ASSET_DIR / "style.css").write_text(STYLE, encoding="utf-8")
    (ASSET_DIR / "site.js").write_text(SCRIPT, encoding="utf-8")


STYLE = """
:root{--sidebar:#343131;--sidebar-dark:#2a2727;--sidebar-link:#d9d9d9;--accent:#2980b9;--accent-dark:#1f5f8b;--text:#30343b;--muted:#68717d;--border:#dfe5ea;--code:#f5f7f9;--paper:#fff}
*{box-sizing:border-box}
html{font-size:16px}
body{margin:0;color:var(--text);background:#edf0f2;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","Microsoft YaHei",Arial,sans-serif;font-size:16px;line-height:1.72;letter-spacing:0}
a{color:var(--accent);text-decoration:none}
a:hover{color:var(--accent-dark);text-decoration:underline}
.wy-nav-side{position:fixed;inset:0 auto 0 0;width:300px;overflow:hidden;background:var(--sidebar);color:var(--sidebar-link)}
.wy-side-scroll{height:100%;overflow-y:auto}
.wy-side-nav-search{background:var(--accent);color:#fff;padding:24px 18px 18px;text-align:center}
.icon-home{display:block;color:#fff;font-size:20px;font-weight:700;line-height:1.25}
.icon-home:hover{color:#fff}
.version{margin:8px 0 16px;font-size:13px;opacity:.85}
#doc-search{width:100%;height:36px;border:0;border-radius:4px;padding:0 10px;color:#333}
.wy-menu{padding:16px 0 32px}
.caption{margin:0;padding:0 20px 8px;color:#55a5d9;font-size:12px;font-weight:700;text-transform:uppercase}
.wy-menu ul{list-style:none;padding:0;margin:0}
.wy-menu a{display:block;color:var(--sidebar-link);padding:10px 20px;border-left:4px solid transparent;font-size:14px;line-height:1.4}
.wy-menu a span{display:block;color:#9db9c9;font-size:12px;margin-bottom:2px}
.wy-menu a.active,.wy-menu a:hover{background:var(--sidebar-dark);border-left-color:var(--accent);color:#fff;text-decoration:none}
.wy-nav-content-wrap{margin-left:300px;min-height:100vh}
.wy-nav-content{background:#fcfcfc;min-height:100vh;padding:38px 56px 88px}
.rst-content{max-width:860px;margin:0 auto}
.breadcrumbs{position:relative;color:var(--muted);font-size:14px;border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:18px}
.breadcrumbs span{margin:0 6px}
.github-link{float:right}
.language-switch{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin:0 0 10px;font-size:14px}
.language-switch span,.language-switch a{border:1px solid var(--border);border-radius:4px;padding:4px 9px}
.language-switch span{background:#f3f6f6;color:#555}
h1,h2,h3{color:#1f2328;font-family:inherit;font-weight:650;line-height:1.32;letter-spacing:0}
h1{font-size:32px;margin:22px 0 12px}
h2{font-size:24px;margin:42px 0 18px;padding:0 0 9px;border-bottom:1px solid var(--border)}
h3{font-size:18px;margin:28px 0 10px;color:#303846;font-weight:650}
h2+h3{margin-top:8px}
.subtitle{color:var(--muted);font-size:16px;margin:-4px 0 28px}
p{margin:0 0 15px}
p+figure,ul+figure,ol+figure,pre+figure{margin-top:24px}
ul,ol{padding-left:1.45rem;margin:10px 0 18px}
li{margin:7px 0;padding-left:2px}
.numbered-list{padding-left:1.55rem}
code{background:var(--code);border:1px solid #d6dde3;border-radius:4px;padding:1px 5px;font-family:Consolas,"SFMono-Regular","Cascadia Mono","Liberation Mono",monospace;font-size:.92em}
pre{background:var(--code);border:1px solid #d6dde3;border-radius:6px;overflow-x:auto;overflow-y:visible;padding:16px 18px;margin:18px 0 24px;line-height:1.55}
pre code{display:block;border:0;padding:0;background:transparent;font-size:14px;white-space:pre}
table{width:100%;border-collapse:collapse;margin:18px 0 24px;background:var(--paper);font-size:15px}
td,th{border:1px solid var(--border);padding:9px 11px;vertical-align:top}
figure{margin:24px 0 30px;text-align:center;overflow-x:auto}
figure img{display:block;width:auto;height:auto;max-width:100%;max-height:76vh;object-fit:contain;margin:0 auto;background:var(--paper);border:1px solid var(--border);border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.admonition{border-left:4px solid var(--accent);background:#eef7fc;padding:12px 16px;margin:18px 0}
.admonition.warning{border-left-color:#c45f18;background:#fff5eb}
.admonition-title{font-weight:700;margin-bottom:6px}
.toctree-wrapper{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-top:16px}
.doc-card{display:block;background:#fff;border:1px solid var(--border);border-radius:6px;padding:14px 16px}
.doc-card:hover{text-decoration:none;border-color:var(--accent)}
.doc-card span{display:inline-block;color:#fff;background:var(--accent);border-radius:3px;padding:1px 6px;font-size:12px;margin-bottom:8px}
.doc-card strong{display:block;color:#222}
.doc-card em{display:block;color:var(--muted);font-style:normal;font-size:14px}
.step{padding-left:12px;border-left:3px solid #d9e8f2;color:#36414d}
.mobile-bar{display:none;align-items:center;gap:12px;background:var(--sidebar);color:#fff;padding:10px 14px}
#menu-toggle{appearance:none;border:1px solid rgba(255,255,255,.35);background:transparent;color:#fff;border-radius:4px;width:34px;height:32px;font-size:20px}
.hidden-by-search{display:none!important}
@media(max-width:900px){
  .wy-nav-side{transform:translateX(-100%);transition:transform .2s ease;z-index:10}
  body.nav-open .wy-nav-side{transform:translateX(0)}
  .wy-nav-content-wrap{margin-left:0}
  .mobile-bar{display:flex;position:sticky;top:0;z-index:5}
  .wy-nav-content{padding:24px 20px 64px}
  .rst-content{max-width:100%}
  figure{margin:18px 0}
  figure img{max-width:100%;max-height:none}
  h1{font-size:28px}
  h2{font-size:22px;margin-top:34px}
  h3{font-size:18px}
  .github-link{float:none;display:block;margin-top:8px}
}
""".strip() + "\n"

SCRIPT = """
const toggle=document.getElementById('menu-toggle');if(toggle){toggle.addEventListener('click',()=>document.body.classList.toggle('nav-open'))}const search=document.getElementById('doc-search');const navItems=Array.from(document.querySelectorAll('#nav-list li'));if(search){search.addEventListener('input',()=>{const q=search.value.trim().toLowerCase();navItems.forEach(item=>{const text=item.textContent.toLowerCase();item.classList.toggle('hidden-by-search',q&&!text.includes(q))})})}
""".strip() + "\n"


def write_root_files(manifest: dict[str, dict[str, int]]) -> None:
    (ROOT / "index.html").write_text('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=zh/index.html"><title>Palm-sized UAV Experiment Manual</title></head><body><p><a href="zh/index.html">\u4e2d\u6587</a> &middot; <a href="en/index.html">English</a></p></body></html>\n', encoding="utf-8")
    (ROOT / ".nojekyll").write_text("", encoding="utf-8")
    (ROOT / "docs-manifest.json").write_text(json.dumps({"source_dir": str(SOURCE_DIR), "manuals": [manual.__dict__ for manual in MANUALS], "stats": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "README.md").write_text("""# Palm-sized UAV Experiment Manual

Bilingual experiment manual for palm-sized UAV summer school labs.

- `zh/` contains Chinese experiment pages, including text, tables, links, commands, and figures.
- `en/` contains English experiment pages with language switches back to the Chinese pages.
- `.github/workflows/pages.yml` deploys the static site with GitHub Pages Actions.

## Local preview

Open `index.html` in a browser, or serve this directory with any static file server.

## Maintenance

```bash
python tools/build_objective_docs.py
```
""", encoding="utf-8")
    workflow = ROOT / ".github" / "workflows"
    workflow.mkdir(parents=True, exist_ok=True)
    (workflow / "pages.yml").write_text("""name: Deploy documentation to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Configure Pages
        uses: actions/configure-pages@v5
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
""", encoding="utf-8")


def main() -> None:
    clean_output()
    write_assets()
    manifest = write_pages()
    write_index("zh")
    write_index("en")
    write_root_files(manifest)
    print(f"Built {len(MANUALS)} objective manuals with {sum(item['images'] for item in manifest.values())} images.")


if __name__ == "__main__":
    main()



