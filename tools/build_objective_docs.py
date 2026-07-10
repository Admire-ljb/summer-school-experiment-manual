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
VIDEO_DIR = ASSET_DIR / "videos"
IMAGE_EN_CURATED_DIR = ASSET_DIR / "images-en-curated"
TRANSLATION_CACHE = ROOT / "tools" / "translation-cache.zh-en.json"
IMAGE_OCR_CACHE = ROOT / "tools" / "image-ocr-cache.json"
FINAL_TEST_SLUG = "manual-13-project-demo"
FINAL_TEST_IMAGE_NAME = "final-comprehensive-test.png"
FINAL_TEST_ZH_SOURCE = ASSET_SOURCE_DIR / "manual-13-final-comprehensive-test-zh.png"
FINAL_TEST_EN_SOURCE = ASSET_SOURCE_DIR / "manual-13-final-comprehensive-test-en.png"
CFCLIENT_TOOLCHAIN_IMAGE_SOURCE = ASSET_SOURCE_DIR / "manual-03-cfclient-python38-toolchain.png"
CFCLIENT_TOOLCHAIN_IMAGE_NAME = "009.png"
DEMO_MATERIAL_SOURCE_DIR = ASSET_SOURCE_DIR / "demo-materials"
DEMO_VIDEO_SOURCE_DIR = ASSET_SOURCE_DIR / "demo-videos"
DEMO_MATERIALS = {
    "manual-04-multiranger": [
        {
            "source": "ranging-simple-arena.jpg",
            "name": "ranging-simple-arena.jpg",
            "zh_title": "简单围栏测距场地",
            "en_title": "Simple Ranging Arena",
            "zh_text": "封闭围栏用于形成稳定的测距边界。测试时可对照无人机与挡板之间的距离变化，检查前、后、左、右方向测距值是否随场地关系同步变化。",
            "en_text": "The enclosed arena provides stable ranging boundaries. During testing, compare the drone-to-baffle distance changes with the front, back, left, and right range readings to check whether the sensor values match the arena geometry.",
        },
    ],
    "manual-06-complex-map": [
        {
            "source": "complex-mapping-arena-reference.jpg",
            "name": "complex-mapping-arena-reference.jpg",
            "zh_title": "复杂建图场地",
            "en_title": "Complex Mapping Arena",
            "zh_text": "场地由外圈挡板和内部障碍组成，适合用于检查无人机在复杂边界中的测距覆盖、航线约束和建图完整性。",
            "en_text": "The arena consists of outer baffles and internal obstacles. It is suitable for checking ranging coverage, route constraints, and mapping completeness in a complex bounded environment.",
        },
        {
            "source": "mapping-pointcloud-result.jpg",
            "name": "mapping-pointcloud-result.jpg",
            "zh_title": "点云建图结果",
            "en_title": "Point-cloud Mapping Result",
            "zh_text": "点云轮廓应与场地外边界和内部挡板位置相对应。局部离散点可作为测距噪声、姿态扰动或遮挡影响的记录，复盘时应结合飞行轨迹一并判断。",
            "en_text": "The point-cloud contour should correspond to the outer boundary and internal baffle positions. Local scattered points can record ranging noise, attitude disturbance, or occlusion effects, and should be interpreted together with the flight trajectory during review.",
        },
    ],
    "manual-11-integrated-practice": [
        {
            "source": "integrated-maze-overview.jpg",
            "name": "integrated-maze-overview.jpg",
            "zh_title": "综合路线场地总览",
            "en_title": "Integrated Route Arena Overview",
            "zh_text": "多通道场地可用于将综合任务拆分为起飞、直线段、转向段、避障段和返航段，并逐段记录实际飞行表现。",
            "en_text": "The multi-corridor arena can be used to divide an integrated task into takeoff, straight-line, turning, obstacle-avoidance, and return segments, with real-flight behavior recorded for each segment.",
        },
    ],
    "manual-13-project-demo": [
        {
            "source": "competition-real-flight-demo.jpg",
            "name": "competition-real-flight-demo.jpg",
            "zh_title": "比赛场地飞行记录",
            "en_title": "Competition Arena Flight Record",
            "zh_text": "比赛型场地记录用于核对起飞区域、通道通过、障碍避让和返航降落等关键环节，评价时应以现场完成情况、日志和视频记录共同作为依据。",
            "en_text": "The competition-style arena record is used to check key stages such as takeoff area, corridor traversal, obstacle avoidance, and return landing. Evaluation should combine on-site completion, logs, and video records.",
        },
    ],
}
DEMO_VIDEOS = {
    "manual-05-ranging": [
        {
            "source": "manual-05-ranging/ranging-enclosed-flight.mp4",
            "name": "ranging-enclosed-flight.mp4",
            "zh_title": "封闭场地避障飞行记录",
            "en_title": "Enclosed-area Obstacle-avoidance Flight Record",
            "zh_text": "该记录用于核对无人机在围栏边界附近的速度、转向和安全距离变化，并与测距阈值日志对应分析。",
            "en_text": "This record is used to check speed, turning, and safety-distance changes near the enclosure boundary, and to compare them with the ranging-threshold logs.",
        },
    ],
    "manual-06-complex-map": [
        {
            "source": "manual-06-complex-map/complex-map-overview-flight.mp4",
            "name": "complex-map-overview-flight.mp4",
            "zh_title": "复杂场地飞行过程",
            "en_title": "Complex-area Flight Process",
            "zh_text": "该记录可与点云结果对照，检查采样区域是否覆盖外圈边界与内部障碍，并定位点云缺口或异常散点的来源。",
            "en_text": "This record can be compared with the point-cloud result to check whether the sampled area covers the outer boundary and internal obstacles, and to locate the source of point-cloud gaps or abnormal scattered points.",
        },
    ],
    "manual-13-project-demo": [
        {
            "source": "manual-13-project-demo/competition-route-flight.mp4",
            "name": "competition-route-flight.mp4",
            "zh_title": "综合任务飞行记录",
            "en_title": "Integrated-task Flight Record",
            "zh_text": "该记录用于复盘通道通过、障碍绕行和返航降落等关键动作，评价时应结合现场完成情况与程序日志。",
            "en_text": "This record is used to review key actions such as corridor traversal, obstacle detour, and return landing. Evaluation should combine on-site completion with program logs.",
        },
    ],
}

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
    Manual("manual-01-vm", 1, "\u5b89\u88c5\u914d\u7f6e\u865a\u62df\u673a", "Virtual Machine Installation and Configuration", "Day1_\u5b9e\u9a8c\u624b\u518c1-\u5b89\u88c5\u914d\u7f6e\u865a\u62df\u673a.docx", "Configure VMware Workstation and install Ubuntu 20.04 as the standard operating environment for all subsequent experiments.", ("Windows host computer with sufficient memory and disk space.", "Course Materials Package: course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe.", "Course Materials Package: course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso."), ("Install VMware Workstation and verify that the new virtual-machine wizard is available.", "Create an Ubuntu virtual machine with appropriate CPU, memory, disk, and NAT network settings.", "Install Ubuntu, perform first-boot setup, install VMware Tools, and create a clean snapshot."), ("Confirm network access from Ubuntu.", "Verify screen scaling and host-to-guest file transfer.", "Restore the clean snapshot once to confirm recovery is available.")),
    Manual("manual-02-ros", 2, "\u914d\u7f6e\u8ba4\u77e5 ROS", "ROS Configuration and Basic Concepts", "Day1_\u5b9e\u9a8c\u624b\u518c2-\u914d\u7f6e\u8ba4\u77e5ROS.docx", "Install ROS and establish the basic concepts used by later robot-control experiments.", ("Ubuntu virtual machine from Manual 1.", "Network access for package installation.", "Terminal access and basic Linux command familiarity."), ("Run the FishROS script from Course Materials Package: course-materials/02_scripts_and_code/04_fishros_install.sh.", "Start roscore and run turtlesim-related commands.", "Use ROS tools to inspect nodes, topics, graphs, and message data."), ("Explain package, node, topic, publisher, and subscriber roles.", "Run turtlesim and teleoperation successfully.", "Use rqt_graph, rqt_plot, rosnode, and rostopic for observation.")),
    Manual("manual-03-crazyflie-setup", 3, "\u521d\u6b21\u914d\u7f6e\u4e0e\u9a71\u52a8 Crazyflie \u65e0\u4eba\u673a", "Initial Crazyflie Configuration and Operation", "Day1_\u5b9e\u9a8c\u624b\u518c3-\u521d\u6b21\u914d\u7f6e\u4e0e\u9a71\u52a8crazyfile\u65e0\u4eba\u673a.docx", "Prepare the Crazyflie software and hardware connection path for safe first operation.", ("Ubuntu/ROS environment from the previous manuals.", "Crazyflie aircraft, battery, USB cable, and Crazyradio.", "Git, internet access, and the Bitcraze crazyflie-clients-python repository checked out at tag 2024.11; cflib and required Python dependencies."), ("Install the Crazyflie client and required libraries.", "Configure USB permissions and radio connection settings.", "Connect to the aircraft and run conservative first-control tests."), ("Crazyflie client starts correctly.", "USB and radio connection can detect the aircraft.", "A short scripted test can be explained and stopped safely.")),
    Manual("manual-04-multiranger", 4, "\u591a\u5411\u6d4b\u8ddd\u4f20\u611f\u5668\u5b9e\u9a8c", "Multi-ranger Sensor Experiment", "Day2_\u5b9e\u9a8c\u624b\u518c1-multiranger.docx", "Read multi-direction distance measurements and connect sensor readings to basic flight behavior.", ("Crazyflie with Multi-ranger deck.", "Working cflib environment.", "Clear indoor test area with simple obstacles."), ("Connect to Crazyflie through cflib.", "Read front, back, left, right, up, and down range values.", "Use threshold rules to generate simple reactive movement."), ("Range values change consistently when obstacles move.", "Students can identify which sensor direction triggered a response.", "The reactive behavior remains inside the safety area.")),
    Manual("manual-05-ranging", 5, "\u6d4b\u8ddd\u8fdb\u9636", "Advanced Ranging Experiment", "Day2_\u5b9e\u9a8c\u624b\u518c2-\u6d4b\u8ddd\u8fdb\u9636.docx", "Extend basic range reading into mission rules and obstacle-aware flight actions.", ("Crazyflie and Multi-ranger deck.", "Validated range-reading script.", "Instructor-confirmed test area."), ("Collect range readings under several obstacle configurations.", "Implement obstacle-triggered actions such as landing, backing away, or bouncing.", "Adjust thresholds and speeds conservatively."), ("The program exits through a safe stop condition.", "Sensor logs support the observed behavior.", "The selected thresholds can be justified from the measurements.")),
    Manual("manual-06-complex-map", 6, "\u590d\u6742\u5730\u56fe\u98de\u884c\u4e0e\u5efa\u56fe", "Complex-map Flight and Mapping", "Day2_\u5b9e\u9a8c\u624b\u518c3-\u590d\u6742\u5730\u56fe\u98de\u884c\u4e0e\u5efa\u56fe.docx", "Use controlled flight and range sensing to explore a more complex obstacle map.", ("Prepared obstacle area.", "Crazyflie with relevant sensing deck.", "Mapping or logging script from the manual."), ("Inspect the map constraints and permitted flight area.", "Run the flight or mapping procedure slowly enough for stable data collection.", "Review the generated obstacle points or map-like output."), ("The flight remains within the allowed area.", "The map output reflects major walls or obstacle regions.", "Failure cases are documented with likely causes.")),
    Manual("manual-07-autonomous-mapping-review", 7, "\u81ea\u4e3b\u5efa\u56fe+\u590d\u4e60", "Autonomous Mapping and Review", "Day2_\u5b9e\u9a8c\u624b\u518c4-\u81ea\u4e3b\u5efa\u56fe+\u590d\u4e60.docx", "Consolidate the ranging and mapping workflow through an autonomous mapping review task.", ("Completed range-sensing and mapping exercises.", "Known test area and flight restrictions.", "Team notes from previous experiments."), ("Review connection, sensing, control, and mapping requirements.", "Design or modify a route that samples useful map areas.", "Run the autonomous mapping task and record the result."), ("The route is reproducible.", "The produced map or log supports the route explanation.", "Main risks and improvements are recorded objectively.")),
    Manual("manual-08-path-planning", 8, "\u8def\u5f84\u89c4\u5212\u4eff\u771f", "Path-planning Simulation", "Day3_\u5b9e\u9a8c\u624b\u518c1-\u8def\u5f84\u89c4\u5212\u4eff\u771f.docx", "Run path-planning simulation experiments and compare route-generation behavior.", ("Course Materials Package: course-materials/00_project_archives/uav_motion_planning.zip.", "Ubuntu environment with required dependencies.", "Terminal access in the project directory."), ("Prepare and build the simulation project as documented.", "Set start and goal conditions in the simulator or visualization tool.", "Run A*, RRT, RRT*, or the provided planning examples and observe outputs."), ("A route is generated for the selected task.", "The observed route can be compared across algorithms or parameters.", "Execution notes include commands, errors, and screenshots where applicable.")),
    Manual("manual-09-cflib", 9, "cflib \u5e93\u7f16\u7a0b", "cflib Programming", "Day3_\u5b9e\u9a8c\u624b\u518c2-cflib\u5e93\u7f16\u7a0b.docx", "Use cflib to structure Crazyflie connection, logging, parameter access, and command scripts.", ("Working Crazyflie connection.", "Python environment with cflib installed.", "Known radio URI or scanning procedure."), ("Initialize CRTP drivers and create a Crazyflie object.", "Use synchronized connection patterns for safer program structure.", "Read parameters or logs and send controlled commands."), ("The script connects and exits cleanly.", "Logged or printed values match the expected aircraft state.", "Motion commands are short, conservative, and explainable.")),
    Manual("manual-10-motion-commander", 10, "\u8fd0\u52a8\u63a7\u5236\u63a5\u53e3\u8fdb\u9636\u7f16\u7a0b", "Advanced Motion Commander Programming", "Day3_\u5b9e\u9a8c\u624b\u518c3-Motion Commander\u8fdb\u9636\u7f16\u7a0b.docx", "Use Motion Commander movement primitives to construct repeatable flight routines.", ("cflib script template.", "Safe test area.", "Instructor-approved height and speed parameters."), ("Create a MotionCommander context.", "Combine takeoff, landing, directional movement, turns, and pauses.", "Test short movement segments before a complete sequence."), ("The drone completes the intended primitive sequence.", "Timing, height, and distance choices are recorded.", "The program can be stopped safely if behavior deviates.")),
    Manual("manual-11-integrated-practice", 11, "\u9636\u6bb5\u7efc\u5408\u5b9e\u8df5", "Integrated Practice", "Day3_\u5b9e\u9a8c\u624b\u518c4-\u9636\u6bb5\u7efc\u5408\u5b9e\u8df5.docx", "Combine setup, sensing, planning, and control skills in a bounded practical task.", ("Completed prior manuals.", "Task area and constraints.", "Team role assignment for operation, monitoring, and recording."), ("Read the task constraints and define success criteria.", "Break the route or behavior into testable components.", "Run the integrated task and record results."), ("The task is completed within the defined constraints.", "The team can explain the selected method.", "Problems are documented with concrete evidence.")),
    Manual("manual-12-position-commander", 12, "\u4f4d\u7f6e\u63a7\u5236\u63a5\u53e3\u5b9e\u9a8c", "PositionCommander", "Day3_\u5b9e\u9a8c\u624b\u518c5-PositionCommander.docx", "Use coordinate-based commands for waypoint routes and structured spatial tasks.", ("Crazyflie setup with appropriate positioning support.", "Coordinate-frame assumptions understood before flight.", "Waypoint list or route sketch."), ("Initialize PositionCommander or the documented position-control API.", "Set default height, speed, and coordinate frame carefully.", "Execute waypoint routes such as square, cube, star, or map-based paths."), ("The coordinate route matches the intended geometry.", "The aircraft remains inside the allowed volume.", "The route can be adjusted by editing explicit coordinates.")),
    Manual("manual-13-project-demo", 13, "\u7efc\u5408\u6bd4\u8d5b\u8bf4\u660e", "Integrated Project Competition", "Day3_\u5b9e\u9a8c\u624b\u518c6-\u7efc\u5408\u9879\u76ee\u5c55\u793a\u4efb\u52a1.docx", "Present the final competition task using the course experiments as technical basis.", ("Competition objective and success criteria.", "Working code and tested hardware setup.", "Presentation evidence such as logs, route sketches, video, or screenshots."), ("Read the competition task and scoring rules.", "Implement and rehearse the workflow under safety constraints.", "Present the method, result, limitations, and improvement plan."), ("The run is executable or reproducible.", "The presentation explains method and evidence objectively.", "Safety, teamwork, and failure handling are included in the report.")),
]


def clean_output() -> None:
    for path in [ROOT / "zh", ROOT / "en", IMAGE_DIR, IMAGE_EN_DIR, VIDEO_DIR]:
        if path.exists():
            shutil.rmtree(path)
    (ROOT / "zh").mkdir(parents=True, exist_ok=True)
    (ROOT / "en").mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_EN_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


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


def copy_cfclient_toolchain_image() -> None:
    if not CFCLIENT_TOOLCHAIN_IMAGE_SOURCE.exists():
        raise FileNotFoundError(f"Missing cfclient toolchain image source: {CFCLIENT_TOOLCHAIN_IMAGE_SOURCE}")
    out_dir = IMAGE_DIR / "manual-03-crazyflie-setup"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CFCLIENT_TOOLCHAIN_IMAGE_SOURCE, out_dir / CFCLIENT_TOOLCHAIN_IMAGE_NAME)


def copy_demo_material_images() -> int:
    copied = 0
    for slug, items in DEMO_MATERIALS.items():
        for item in items:
            source = DEMO_MATERIAL_SOURCE_DIR / item["source"]
            if not source.exists():
                raise FileNotFoundError(f"Missing demo material image source: {source}")
            data = optimize_image_bytes(source.read_bytes(), source.suffix.lower() or ".jpg")
            for image_root in [IMAGE_DIR, IMAGE_EN_DIR]:
                out_dir = image_root / slug
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / item["name"]).write_bytes(data)
            copied += 1
    return copied


def copy_demo_videos() -> int:
    copied = 0
    for slug, items in DEMO_VIDEOS.items():
        for item in items:
            source = DEMO_VIDEO_SOURCE_DIR / item["source"]
            if not source.exists():
                raise FileNotFoundError(f"Missing demo video source: {source}")
            out_dir = VIDEO_DIR / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, out_dir / item["name"])
            copied += 1
    return copied


def relationship_map(zf: zipfile.ZipFile) -> dict[str, str]:
    rels_path = "word/_rels/document.xml.rels"
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    return {rel.attrib["Id"]: rel.attrib["Target"] for rel in root if "Id" in rel.attrib and "Target" in rel.attrib}


def text_from(element: ET.Element, preserve: bool = False) -> str:
    text = "".join(node.text or "" for node in element.findall(".//w:t", NS))
    if preserve:
        text = text.replace("\u00a0", " ")
    return text.rstrip() if preserve else text.strip()


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
    if re.match(r"^(sudo|pip|python|python3|ros|rosrun|roslaunch|catkin|source|git|cd|mkdir|touch|cat|ping|reboot)\b", stripped):
        return True
    if stripped in {"EOF", "EOT"}:
        return True
    if re.match(r"^(import\b|from\b|def\b|class\b|if __name__|for |while |with |try:|except|return\b|print\(|#)", stripped):
        return True
    if re.match(r"^(SUBSYSTEM==|[a-z_][a-z0-9_]*\([^)]*\)\s*/\s*[a-z_][a-z0-9_]*\()", stripped):
        return True
    return False


def is_code_style(style: str) -> bool:
    return style.strip().lower() in {"html", "code", "sourcecode", "source code"}


def is_code_candidate(block: Block) -> bool:
    return (
        isinstance(block, ParagraphBlock)
        and not block.images
        and (is_code_style(block.style) or (bool(block.text.strip()) and is_code_like(block.text)))
    )


def is_code_block(block: Block) -> bool:
    return is_code_candidate(block) and bool(block.text.strip())


CODE_COMPLETIONS = {
    "def move_linear_simple(scf):\n    ...": """def move_linear_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)
        mc.back(0.5)
        time.sleep(1)""",
    "def take_off_simple(scf):\n    ...": """def take_off_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT):
        time.sleep(2)""",
    "def log_pos_callback(timestamp, data, logconf):\n    ...": """def log_pos_callback(timestamp, data, logconf):
    print(data)
    global position_estimate
    position_estimate[0] = data['stateEstimate.x']
    position_estimate[1] = data['stateEstimate.y']""",
    "def param_deck_flow(name, value_str):\n    ...": """def param_deck_flow(name, value_str):
    value = int(value_str)
    print(value)
    if value:
        deck_attached_event.set()
        print('Deck is attached!')
    else:
        print('Deck is NOT attached!')""",
}


CODE_TEXT_REPLACEMENTS = {
    "radio://0/60/2M/注意改成对的硬件地址": "radio://0/60/2M/E7E7E7E7E1",
    "radio://0/80/2M/注意改成对的硬件地址": "radio://0/80/2M/E7E7E7E7E2",
    "radio://0/80/2M/E7E7E7E3改成正确的硬件地址": "radio://0/80/2M/E7E7E7E3",
    "radio://0/80/2M/E7E7E7E7E3改成正确的硬件地址": "radio://0/80/2M/E7E7E7E7E3",
    "# 只要可以继续飞行就循环执行": "# Continue the loop while flight is allowed",
    "# 检查上方有没有障碍物": "# Check whether an obstacle is above the drone",
    "#有障碍物！停止飞行": "# Obstacle detected; stop flying",
    "# 检查前方有没有障碍物": "# Check whether an obstacle is in front of the drone",
    "# 命令无人机以设定速度飞行": "# Command the drone to fly at the configured speed",
}


def normalize_code_text(code: str) -> str:
    code = code.replace("\u00a0", " ")
    code = code.replace("\n(...)\n", "\n")
    code = code.replace(
        "def move_box_limit(scf):\n"
        "    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:\n"
        "        while (1):",
        "def move_box_limit(scf):\n"
        "    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:\n"
        "        mc.start_forward()\n"
        "        while True:",
    )
    code = code.replace(
        "            elif position_estimate[0] < -BOX_LIMIT:\n"
        "                mc.start_forward()\n"
        "def move_linear_simple(scf):",
        "            elif position_estimate[0] < -BOX_LIMIT:\n"
        "                mc.start_forward()\n"
        "            time.sleep(0.1)\n"
        "def move_linear_simple(scf):",
    )
    for source, replacement in CODE_TEXT_REPLACEMENTS.items():
        code = code.replace(source, replacement)
    for placeholder, replacement in CODE_COMPLETIONS.items():
        code = code.replace(placeholder, replacement)
    return code


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
                style = paragraph_style(child)
                text = text_from(child, preserve=is_code_style(style))
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
                    blocks.append(ParagraphBlock(text, style, tuple(images)))
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
            while index < len(blocks) and is_code_candidate(blocks[index]):
                code_lines.append(blocks[index].text.rstrip())  # type: ignore[union-attr]
                index += 1
            while code_lines and not code_lines[0].strip():
                code_lines.pop(0)
            while code_lines and not code_lines[-1].strip():
                code_lines.pop()
            code_text = normalize_code_text(chr(10).join(code_lines))
            rendered.append(f"<pre><code>{html.escape(code_text)}</code></pre>")
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


def manual_label(manual: Manual, lang: str) -> str:
    if manual.slug == FINAL_TEST_SLUG:
        return "\u6bd4\u8d5b\u8bf4\u660e" if lang == "zh" else "Competition"
    return f"\u5b9e\u9a8c {manual.number}" if lang == "zh" else f"Experiment {manual.number}"


def manual_display_title(manual: Manual, lang: str) -> str:
    return manual.zh_title if lang == "zh" else manual.en_title


def nav_html(lang: str, current_slug: str | None = None) -> str:
    home = "\u9996\u9875" if lang == "zh" else "Home"
    items = [f'<li><a class="{"active" if current_slug is None else ""}" href="index.html">{home}</a></li>']
    for manual in MANUALS:
        if manual.slug == FINAL_TEST_SLUG:
            section = "\u6bd4\u8d5b\u8bf4\u660e" if lang == "zh" else "Competition"
            items.append(f'<li class="nav-group">{section}</li>')
        title = manual_display_title(manual, lang)
        label = manual_label(manual, lang)
        active = " active" if current_slug == manual.slug else ""
        items.append(f'<li><a class="{active.strip()}" href="{manual.slug}.html"><span>{label}</span>{html.escape(title)}</a></li>')
    return "\n".join(items)

def layout(lang: str, title: str, body: str, current_slug: str | None = None) -> str:
    zh_href = "index.html" if lang == "zh" else f"../zh/{'index.html' if current_slug is None else current_slug + '.html'}"
    en_href = "index.html" if lang == "en" else f"../en/{'index.html' if current_slug is None else current_slug + '.html'}"
    language_switch = (
        f'<span>\u4e2d\u6587</span><a href="{en_href}">English</a>'
        if lang == "zh"
        else f'<a href="{zh_href}">Chinese</a><span>English</span>'
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
            "<div class=\"admonition\"><p class=\"admonition-title\">\u8bfe\u7a0b\u8d44\u6599\u5305</p>"
            "<p>\u8bfe\u7a0b\u8d44\u6599\u5305\u6587\u4ef6\u5939\u540d\u4e3a <code>course-materials</code>\uff0c\u53ef\u901a\u8fc7 <a href=\"https://bhpan.buaa.edu.cn/link/AA5DF49653676B4EDFBAB8B2A09B0FBEE9\">\u5317\u822a\u7f51\u76d8\u94fe\u63a5</a> \u4e0b\u8f7d\uff0c\u6709\u6548\u671f\u81f3 2028-11-11 10:31\u3002\u4e0b\u8f7d\u540e\u8bf7\u89e3\u538b\u4e3a <code>course-materials</code> \u6587\u4ef6\u5939\uff0c\u4ee5\u4fbf\u4e0e\u672c\u6587\u6863\u4e2d\u7684\u8def\u5f84\u4fdd\u6301\u4e00\u81f4\u3002</p></div>"
            "<h2>\u5b9e\u9a8c\u76ee\u5f55</h2><div class=\"toctree-wrapper\">"
        )
        competition_card = ""
        for manual in MANUALS:
            card = f'<a class="doc-card" href="{manual.slug}.html"><span>{manual_label(manual, "zh")}</span><strong>{html.escape(manual_display_title(manual, "zh"))}</strong><em>{html.escape(manual.en_title)}</em></a>\n'
            if manual.slug == FINAL_TEST_SLUG:
                competition_card = card
            else:
                body += card
        body += '</div><h2>\u6bd4\u8d5b\u8bf4\u660e</h2><div class="toctree-wrapper">' + competition_card + '</div>'
        title = "\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u624b\u518c"
    else:
        body = "<h1>Palm-sized UAV Experiment Manual</h1><p>This manual covers environment setup, sensor use, path-planning simulation, cflib programming, flight-control routines, and integrated project tasks for palm-sized UAV experiments.</p><div class=\"admonition warning\"><p class=\"admonition-title\">Safety note</p><p>Experiments involving real flight must be conducted only after the instructor or teaching assistant confirms the arena, equipment, batteries, and emergency-stop procedure.</p></div><div class=\"admonition\"><p class=\"admonition-title\">Course Materials Package</p><p>Download the <code>course-materials</code> folder from the <a href=\"https://bhpan.buaa.edu.cn/link/AA5DF49653676B4EDFBAB8B2A09B0FBEE9\">BUAA cloud link</a>. The link is valid until November 11, 2028 at 10:31. After downloading, extract it as <code>course-materials</code> so the paths in this manual match the folder name.</p></div><h2>Experiment list</h2><div class=\"toctree-wrapper\">"
        competition_card = ""
        for manual in MANUALS:
            card = f'<a class="doc-card" href="{manual.slug}.html"><span>{manual_label(manual, "en")}</span><strong>{html.escape(manual_display_title(manual, "en"))}</strong></a>\n'
            if manual.slug == FINAL_TEST_SLUG:
                competition_card = card
            else:
                body += card
        body += '</div><h2>Competition Brief</h2><div class="toctree-wrapper">' + competition_card + '</div>'
        title = "Palm-sized UAV Experiment Manual"
    (ROOT / lang / "index.html").write_text(layout(lang, title, body), encoding="utf-8")

def english_body(manual: Manual, blocks: list[Block], cache: dict[str, str], image_map: dict[str, str]) -> str:
    return f"""
<h1>Experiment {manual.number}: {html.escape(manual.en_title)}</h1>
{render_blocks(blocks, "en", cache, image_map)}
"""


def wall_following_examples(lang: str) -> str:
    if lang == "zh":
        return '''
<div class="admonition"><p class="admonition-title">官方示例仓库：Multiranger Wall Following</p>
<p><code>wall_following.py</code> 和 <code>multiranger_wall_following.py</code> 来源于 Bitcraze 官方 <code>crazyflie-demos</code> 仓库。课堂以官方仓库中的文件为准，手册列出来源和使用方式。</p>
<ul>
<li>仓库主页：<a href="https://github.com/bitcraze/crazyflie-demos/tree/main">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li>
<li>示例目录：<a href="https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_wall_following">demos/scripts/cflib/multiranger/multiranger_wall_following</a></li>
<li><code>wall_following.py</code>：<a href="https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_wall_following/wall_following.py">官方文件链接</a></li>
<li><code>multiranger_wall_following.py</code>：<a href="https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_wall_following/multiranger_wall_following.py">官方文件链接</a></li>
</ul></div>
<p>建议在虚拟机中按以下方式使用：</p>
<pre><code>cd ~/workspace
git clone https://github.com/bitcraze/crazyflie-demos.git
cd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_wall_following
python3 multiranger_wall_following.py</code></pre>
<p>运行前请确认 Crazyflie、Crazyradio、Flow deck 和 Multi-ranger deck 已连接正常；将脚本中的 <code>URI</code> 或环境变量 <code>CFLIB_URI</code> 设置为所在小组分配的完整 radio URI；首次测试应在低速、空旷、安全的场地中进行，并先确认悬停和急停方式。</p>
'''
    return '''
<div class="admonition"><p class="admonition-title">Official demo repository: Multiranger Wall Following</p>
<p><code>wall_following.py</code> and <code>multiranger_wall_following.py</code> come from Bitcraze's official <code>crazyflie-demos</code> repository. Use the files in the official repository as the source of record; this manual lists the source links and classroom usage steps.</p>
<ul>
<li>Repository: <a href="https://github.com/bitcraze/crazyflie-demos/tree/main">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li>
<li>Demo directory: <a href="https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_wall_following">demos/scripts/cflib/multiranger/multiranger_wall_following</a></li>
<li><code>wall_following.py</code>: <a href="https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_wall_following/wall_following.py">official file link</a></li>
<li><code>multiranger_wall_following.py</code>: <a href="https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_wall_following/multiranger_wall_following.py">official file link</a></li>
</ul></div>
<p>Recommended usage in the virtual machine:</p>
<pre><code>cd ~/workspace
git clone https://github.com/bitcraze/crazyflie-demos.git
cd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_wall_following
python3 multiranger_wall_following.py</code></pre>
<p>Before running the demo, confirm that the Crazyflie, Crazyradio, Flow deck, and Multi-ranger deck are connected correctly. Set <code>URI</code> in the script or the <code>CFLIB_URI</code> environment variable to the full radio URI assigned to your group. For the first test, use a low-speed, open, safe area and confirm hover and emergency-stop behavior first.</p>
'''


def apply_wall_following_examples(manual: Manual, lang: str, body: str) -> str:
    if "Official demo repository: Multiranger Wall Following" in body:
        return body
    if "官方示例仓库：Multiranger Wall Following" in body:
        return body
    examples = wall_following_examples(lang)
    if lang == "zh":
        marker = "<p>将该节课附上的wall_following.py和multiranger_wall_following.py拷贝至虚拟机中。其中将multiranger_wall_following.py放在workspace目录下，在workspace目录下再新建一个名为wall_following的目录，将wall_following.py文件放入其中，以完成multiranger_wall_following.py文件运行所需要的依赖。</p>"
    else:
        marker = "<p>Copy the wall_following.py and multiranger_wall_following.py attached to this lesson to the virtual machine. Place multiranger_wall_following.py in the workspace directory, create a new directory named wall_following in the workspace directory, and put the wall_following.py file into it to complete the dependencies required to run the multiranger_wall_following.py file.</p>"
    if marker in body:
        return body.replace(marker, examples, 1)
    return body + examples

def apply_course_material_overrides(manual: Manual, lang: str, body: str) -> str:
    common_pairs = {
        "<p>本次实验将主要进行python脚本的运行，所有的编程库的调用，皆来自于官方的网址教程：用户指南 |比特热潮</p>":
        "<p>本次实验将主要进行python脚本的运行，编程库参考资料可直接打开 Bitcraze cflib User Guides：</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/user-guides/</code></pre>",
        "<p>若在进行实验中遇到一些困难，也可点击上述网址进行进一步的参考。同时部分操作和知识要点也在上节课的实验手册中有提及，如有不会的地方可以再参考上节的实验手册，这部分操作这节实验手册不再赘述。</p>":
        "<p>若在进行实验中遇到困难，可直接打开上述网址进一步参考。同时部分操作和知识要点也在上节课的实验手册中有提及，如有不会的地方可以再参考上节的实验手册，这部分操作这节实验手册不再赘述。</p>",
        "<p>This experiment will mainly run python scripts. All programming library calls come from the official website tutorial: User Guide | Bit Boom</p>":
        "<p>This experiment mainly runs Python scripts. Open the Bitcraze cflib User Guides directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/user-guides/</code></pre>",
        "<p>If you encounter some difficulties during the experiment, you can also click on the above URL for further reference. At the same time, some operations and knowledge points are also mentioned in the experiment manual of the previous class. If you have any questions, you can refer to the experiment manual of the previous section. This part of the operation will not be repeated in this experiment manual.</p>":
        "<p>If you encounter difficulties during the experiment, open the URL listed above for further reference. Some operations and knowledge points are also mentioned in the previous experiment manual; this part is not repeated here.</p>",
        "<p>统一配置：8GB</p>\n\n<p>保留至少8GB内存给物理机。</p>":
        "<p>统一配置：8GB</p>\n<p>保留至少8GB内存给物理机。</p>",
        "<p>Unified configuration: 8GB</p>\n\n<p>Reserve at least 8GB of memory for the host machine.</p>":
        "<p>Unified configuration: 8GB</p>\n<p>Reserve at least 8GB of memory for the host machine.</p>",
        "<p>再下一步让脚本自动帮助我们选择下载速度最快的源，输入数字1按回车键。</p>":
        "<p>再下一步让脚本自动帮助我们选择访问速度最快的软件源，输入数字1按回车键。</p>",
        "<p>The next step is to let the script automatically help us select the source with the fastest download speed. Enter the number 1 and press Enter.</p>":
        "<p>The next step is to let the script automatically help us select the fastest software mirror. Enter the number 1 and press Enter.</p>",
        "<p>再输入以下命令配置一下pip3下载的软件源：</p>":
        "<p>再输入以下命令配置一下pip3使用的软件源：</p>",
        "<p>Then enter the following command to configure the software source downloaded by pip3:</p>":
        "<p>Then enter the following command to configure the software source used by pip3:</p>",
        "<p>课堂用途：用于提高 pip 下载 Python 依赖的速度和稳定性。</p>":
        "<p>课堂用途：用于提高 pip 安装 Python 依赖时的软件源访问速度和稳定性。</p>",
        "<p>Classroom use: Used to improve the speed and stability of pip downloading Python dependencies.</p>":
        "<p>Classroom use: Used to improve the speed and stability of pip access when installing Python dependencies.</p>",
        "<li>手册中的用途是设置 pip index-url，让 cflib、GUI 客户端和相关依赖更快下载。</li>":
        "<li>手册中的用途是设置 pip index-url，让 cflib、GUI 客户端和相关依赖安装时使用清华镜像源。</li>",
        "<li>The purpose in the manual is to set the pip index-url so that cflib, GUI client and related dependencies can be downloaded faster.</li>":
        "<li>The purpose in the manual is to set the pip index-url so that cflib, the GUI client, and related dependencies use the Tsinghua mirror source during installation.</li>",
    }
    manual_pairs: dict[str, dict[str, str]] = {
        "manual-01-vm": {
            "<h3>软件资源（可从官网下载，为节省时间由助教拷贝）</h3>\n<p>VMware Workstation Pro 16</p>\n<p>Ubuntu 20.04 LTS Desktop版镜像文件</p>":
            "<h3>软件资源（从course-materials获取）</h3>\n<p>VMware Workstation Pro 16：<code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code></p>\n<p>Ubuntu 20.04 LTS Desktop版镜像文件：<code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code></p>",
            "<h3>Software resources (can be downloaded from the official website, copied by the teaching assistant to save time)</h3>\n<p>VMware Workstation Pro 16</p>\n<p>Ubuntu 20.04 LTS Desktop version image file</p>":
            "<h3>Software resources (from the Course Materials Package)</h3>\n<p>VMware Workstation Pro 16: <code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code></p>\n<p>Ubuntu 20.04 LTS Desktop image file: <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code></p>",
            "<p>具体图文流程在浏览器中打开此链接：</p>":
            "<p>具体图文流程可直接打开以下网址：</p>",
            "<p>For the specific graphic process, open this link in your browser:</p>":
            "<p>For the specific illustrated process, open this URL directly:</p>",
            "<h3>下载与安装</h3>\n<p>访问VMware官网，下载Workstation Pro 16安装包。</p>":
            "<h3>从course-materials安装</h3>\n<p>在course-materials中找到 <code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code>。</p>",
            "<h3>Download and install</h3>\n<p>Visit the VMware official website and download the Workstation Pro 16 installation package.</p>":
            "<h3>Install from the Course Materials Package</h3>\n<p>In the Course Materials Package, locate <code>course-materials/04_virtual_machine_resources/VMware-workstation-full-16.2.5-20904516.exe</code>.</p>",
            "<p>具体参考图文流程在浏览器中打开此链接：</p>":
            "<p>具体参考图文流程可直接打开以下网址：</p>",
            "<p>Please refer to the graphic process for specific details and open this link in your browser:</p>":
            "<p>For the illustrated reference process, open this URL directly:</p>",
            "<p>该界面中点击浏览选中ubuntu20.04系统映像文件，点击下一步</p>":
            "<p>该界面中点击浏览，选择course-materials中的 <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code>，点击下一步</p>",
            "<p>In this interface, click Browse to select the ubuntu20.04 system image file, and click Next</p>":
            "<p>In this interface, click Browse, select <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code> from the Course Materials Package, and click Next</p>",
            "<p>在虚拟机设置中，选择CD/DVD驱动器，加载下载的Ubuntu 20.04 ISO文件。</p>":
            "<p>在虚拟机设置中，选择CD/DVD驱动器，加载course-materials中的 <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code>。</p>",
            "<p>In the virtual machine settings, select the CD/DVD drive and load the downloaded Ubuntu 20.04 ISO file.</p>":
            "<p>In the virtual machine settings, select the CD/DVD drive and load <code>course-materials/04_virtual_machine_resources/ubuntu-20.04.6-desktop-amd64.iso</code> from the Course Materials Package.</p>",
            "<p>课堂用途：辅助完成 Ubuntu 镜像下载、虚拟机创建、系统安装和国内镜像源配置。</p>":
            "<p>课堂用途：辅助完成 Ubuntu 镜像选择、虚拟机创建、系统安装和国内镜像源配置。</p>",
            "<p>Class purpose: Assist in completing Ubuntu image download, virtual machine creation, system installation and domestic image source configuration.</p>":
            "<p>Class purpose: Assist in selecting the Ubuntu image, creating the virtual machine, installing the system, and configuring domestic mirror sources.</p>",
        },
        "manual-02-ros": {
            "<p>在这里将会一个开源的脚本一键安装配置ROS环境，利用该脚本配置ROS系统将会极为方便，适合初学者快速上手ROS。同时也向同学们推荐一些网络教学视频，学有余力的同学可以对照视频进行ROS学习的巩固和拓展：</p>":
            "<p>这里使用course-materials中的 FishROS 一键安装脚本配置 ROS 环境。脚本位置为 <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code>。利用该脚本配置ROS系统将会极为方便，适合初学者快速上手ROS。同时也向同学们推荐一些网络教学视频，学有余力的同学可以对照视频进行ROS学习的巩固和拓展：</p>",
            "<p>Here we will use an open source script to install and configure the ROS environment with one click. Using this script to configure the ROS system will be extremely convenient and suitable for beginners to quickly get started with ROS. At the same time, we also recommend some online teaching videos to students. Students who are willing to learn can refer to the videos to consolidate and expand their ROS learning:</p>":
            "<p>Here we use the FishROS one-click installation script from the Course Materials Package to configure the ROS environment. The script is located at <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code>. Using this script to configure the ROS system is convenient for beginners. At the same time, we also recommend some online teaching videos to students. Students who are willing to learn can refer to the videos to consolidate and expand their ROS learning:</p>",
            "<p>打开虚拟机，进入主界面后呼出终端（鼠标点击一下桌面后，同时按住ctrl+alt+T键，参考第一节课的实验手册。）</p>\n<p>在终端中输入如下命令(可以右键选中如下命令点击复制，再粘贴到终端中)：</p>\n<p>wget http://fishros.com/install -O fishros &amp;&amp; . fishros</p>":
            "<p>先将 <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code> 拖入虚拟机的用户目录或 <code>workspace</code> 文件夹中。打开虚拟机，进入主界面后呼出终端（鼠标点击一下桌面后，同时按住ctrl+alt+T键，参考第一节课的实验手册。）</p>\n<p>在脚本所在目录中输入如下命令运行脚本：</p>\n<pre><code>cp 04_fishros_install.sh fishros\n. fishros</code></pre>\n<p>该脚本本身已经放在course-materials中，但安装 ROS 和系统依赖时仍需要虚拟机联网。</p>",
            "<p>Open the virtual machine, enter the main interface and call out the terminal (after clicking the mouse on the desktop, press and hold the ctrl+alt+T keys at the same time, refer to the experiment manual of the first lesson.)</p>\n<p>Enter the following command in the terminal (you can right-click to select the following command, click copy, and then paste it into the terminal):</p>\n<p>wget http://fishros.com/install -O fishros &amp;&amp; . fishros</p>":
            "<p>First drag <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code> into the virtual machine user directory or the <code>workspace</code> folder. Open the virtual machine, enter the main interface and call out the terminal (after clicking the mouse on the desktop, press and hold the ctrl+alt+T keys at the same time, refer to the experiment manual of the first lesson.)</p>\n<p>In the directory containing the script, enter the following commands to run it:</p>\n<pre><code>cp 04_fishros_install.sh fishros\n. fishros</code></pre>\n<p>The script file is included in the Course Materials Package, but installing ROS and system dependencies still requires network access inside the virtual machine.</p>",
            "<p>课堂用途：用于通过命令行下载并运行 ROS 安装脚本。</p>\n<ul>\n<li>手册中的命令为：wget http://fishros.com/install -O fishros &amp;&amp; . fishros</li>":
            "<p>课堂用途：用于从course-materials运行 ROS 安装脚本。</p>\n<ul>\n<li>course-materials位置：<code>course-materials/02_scripts_and_code/04_fishros_install.sh</code></li>\n<li>手册中的运行命令为：<code>cp 04_fishros_install.sh fishros</code>，然后执行 <code>. fishros</code></li>",
            "<p>Classroom use: Used to download and run the ROS installation script through the command line.</p>\n<ul>\n<li>The command in the manual is: wget http://fishros.com/install -O fishros &amp;&amp; . fishros</li>":
            "<p>Classroom use: Used to run the ROS installation script from the Course Materials Package.</p>\n<ul>\n<li>Course Materials Package location: <code>course-materials/02_scripts_and_code/04_fishros_install.sh</code></li>\n<li>Run it with: <code>cp 04_fishros_install.sh fishros</code>, then <code>. fishros</code></li>",
        },
        "manual-03-crazyflie-setup": {
            "<p>直接用图形化操作的方法，在主机windows的文件界面将软件包拖动进linux虚拟机的文件界面即可。</p>":
            """<p>本节使用 Git 安装 cfclient，并固定到 Bitcraze 官方仓库的 <code>2024.11</code> 版本，避免来源和版本不一致。打开虚拟机终端，先进入 workspace 并获取源码：</p>
<pre><code>mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/bitcraze/crazyflie-clients-python.git
cd crazyflie-clients-python
git checkout 2024.11</code></pre>""",
            "<p>Directly use the graphical operation method to drag the software package into the file interface of the Linux virtual machine from the file interface of the host windows.</p>":
            """<p>Install cfclient with Git and fix the source to the official Bitcraze <code>2024.11</code> version so that the source and version are explicit. Open a terminal in the virtual machine, enter <code>workspace</code>, and get the source code:</p>
<pre><code>mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/bitcraze/crazyflie-clients-python.git
cd crazyflie-clients-python
git checkout 2024.11</code></pre>""",
            "<p>再双击该压缩包，点击extract解压至该文件目录下。</p>":
            "<p>如果已经克隆过该仓库，不需要重新下载；进入已有目录后执行 <code>git fetch --tags</code>，再执行 <code>git checkout 2024.11</code>。确认当前终端目录为 <code>~/workspace/crazyflie-clients-python</code>，后续依赖安装和 <code>cfclient</code> 安装命令均在该目录中执行。</p>",
            "<p>Double-click the compressed package and click extract to extract it to the file directory.</p>":
            "<p>If the repository has already been cloned, do not download it again. Enter the existing directory, run <code>git fetch --tags</code>, and then run <code>git checkout 2024.11</code>. Confirm that the current terminal directory is <code>~/workspace/crazyflie-clients-python</code>; run the dependency and <code>cfclient</code> installation commands from this directory.</p>",
            "<p>具体的无人机基础认知教程可参考该官方网址：Getting started with the Crazyflie 2.0 or Crazyflie 2.1(+) | Bitcraze</p>":
            "<p>具体的无人机基础认知教程可直接打开 Bitcraze 官方教程：</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-crazyflie-2-x/</code></pre>",
            "<p>For specific basic drone cognition tutorials, please refer to this official website: Getting started with the Crazyflie 2.0 or Crazyflie 2.1(+) | Bitcraze</p>":
            "<p>For the basic Crazyflie tutorial, open the official Bitcraze tutorial directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-crazyflie-2-x/</code></pre>",
            "<p>首先先配置linux虚拟机中的usb设备的权限，详细的操作可以再参考官方网址的教程：</p>\n<p>USB permissions | Bitcraze</p>":
            "<p>首先先配置linux虚拟机中的usb设备的权限，详细操作可直接打开 Bitcraze USB permissions 页面：</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/installation/usb_permissions/</code></pre>",
            "<p>First, configure the permissions of the USB device in the Linux virtual machine. For detailed operations, you can refer to the tutorial on the official website:</p>\n<p>USB permissions | Bitcraze</p>":
            "<p>First, configure the permissions of the USB device in the Linux virtual machine. For detailed operations, open the Bitcraze USB permissions page directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/installation/usb_permissions/</code></pre>",
            "<p>补充，实验官方教程网址为：https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</p>":
            "<p>补充，实验官方教程网址为：</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</code></pre>",
            "<p>Supplement, the official tutorial website for the experiment is: https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</p>":
            "<p>Supplement: open the official experiment tutorial directly:</p>\n<pre><code>https://www.bitcraze.io/documentation/tutorials/getting-started-with-stem-drone-bundle/</code></pre>",
        },
        "manual-04-multiranger": {
            "<p>该模块的官方教程网址：Multi-ranger deck | Bitcraze</p>":
            "<p>该模块的产品说明可直接打开 Bitcraze 页面：</p>\n<pre><code>https://store.bitcraze.io/products/multi-ranger-deck</code></pre>",
            "<p>The official tutorial URL of this module: Multi-ranger deck | Bitcraze</p>":
            "<p>Open the Bitcraze product page for this module directly:</p>\n<pre><code>https://store.bitcraze.io/products/multi-ranger-deck</code></pre>",
        },
        "manual-06-complex-map": {
            "<p>将本节课附带的multiranger_pointcloud.py文件放入workspace中，该python脚本可直接运行。如下图所示，该程序的主要功能为crazyflie无人机在障碍环境中使用multiranger模块进行周边障碍物的点云地图建图。</p>":
            "<div class=\"admonition\"><p class=\"admonition-title\">官方示例仓库：Multiranger Point Cloud</p><p><code>multiranger_pointcloud.py</code> 来源于 Bitcraze 官方 <code>crazyflie-demos</code> 仓库。课堂以官方仓库中的文件为准，手册列出来源和使用方式。</p><ul><li>仓库主页：<a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main\">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li><li>示例目录：<a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_pointcloud\">demos/scripts/cflib/multiranger/multiranger_pointcloud</a></li><li><code>multiranger_pointcloud.py</code>：<a href=\"https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_pointcloud/multiranger_pointcloud.py\">官方文件链接</a></li></ul></div><p>建议在虚拟机中按以下方式使用：</p><pre><code>cd ~/workspace\ngit clone https://github.com/bitcraze/crazyflie-demos.git\ncd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_pointcloud\npython3 multiranger_pointcloud.py</code></pre><p>运行前请确认 Crazyflie、Crazyradio、Flow deck 和 Multi-ranger deck 已连接正常；该示例需要图形界面和 Python 可视化依赖，若提示缺少依赖，请根据官方 README 安装 <code>numpy</code>、<code>vispy</code> 和 <code>PyQt6</code>。首次运行应在安全场地中进行，并确认窗口关闭后无人机会正常降落。</p>",
            "<p>Put the multiranger_pointcloud.py file attached to this lesson into the workspace, and the python script can be run directly. As shown in the figure below, the main function of this program is to use the multiranger module of the crazyflie drone in an obstacle environment to construct point cloud maps of surrounding obstacles.</p>":
            "<div class=\"admonition\"><p class=\"admonition-title\">Official demo repository: Multiranger Point Cloud</p><p><code>multiranger_pointcloud.py</code> comes from Bitcraze's official <code>crazyflie-demos</code> repository. Use the file in the official repository as the source of record; this manual lists the source link and classroom usage steps.</p><ul><li>Repository: <a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main\">https://github.com/bitcraze/crazyflie-demos/tree/main</a></li><li>Demo directory: <a href=\"https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_pointcloud\">demos/scripts/cflib/multiranger/multiranger_pointcloud</a></li><li><code>multiranger_pointcloud.py</code>: <a href=\"https://github.com/bitcraze/crazyflie-demos/blob/main/demos/scripts/cflib/multiranger/multiranger_pointcloud/multiranger_pointcloud.py\">official file link</a></li></ul></div><p>Recommended usage in the virtual machine:</p><pre><code>cd ~/workspace\ngit clone https://github.com/bitcraze/crazyflie-demos.git\ncd crazyflie-demos/demos/scripts/cflib/multiranger/multiranger_pointcloud\npython3 multiranger_pointcloud.py</code></pre><p>Before running the demo, confirm that the Crazyflie, Crazyradio, Flow deck, and Multi-ranger deck are connected correctly. This example requires a graphical desktop and Python visualization dependencies; if dependencies are missing, install <code>numpy</code>, <code>vispy</code>, and <code>PyQt6</code> according to the official README. Run the first test in a safe area and confirm that the drone lands normally after the visualization window is closed.</p>",
        },
        "manual-08-path-planning": {
            "<p>同时再打开本机上存放今天实验所需要的工程文件压缩包的所在位置（该压缩包放在电脑桌面或者某个文件夹都可以）。鼠标选中本机上的压缩包文件，直接拖动到虚拟机中的workspace中。</p>":
            "<p>同时打开course-materials中的项目压缩文件位置：<code>course-materials/00_project_archives/uav_motion_planning.zip</code>。鼠标选中该压缩包文件，直接拖动到虚拟机中的workspace中。</p>",
            "<p>At the same time, open the location on the local computer where the compressed package of project files required for today&#x27;s experiment is stored (the compressed package can be placed on the computer desktop or in a certain folder). Select the compressed package file on the local machine with the mouse and drag it directly to the workspace in the virtual machine.</p>":
            "<p>At the same time, open the project archive in the Course Materials Package: <code>course-materials/00_project_archives/uav_motion_planning.zip</code>. Select this archive on the host machine and drag it directly into <code>workspace</code> in the virtual machine.</p>",
            "<p>接下来输入以下命令（可能会因为无法连接到外网而失败，可以多试几次）:</p>":
            "<p>接下来输入以下命令（如虚拟机缺少系统依赖或软件源不可用，可能需要先检查网络或离线源配置）:</p>",
            "<p>Next enter the following command (it may fail because you cannot connect to the external network, you can try a few more times):</p>":
            "<p>Next enter the following command (if system dependencies are missing or the software source is unavailable, check the network or offline-source configuration first):</p>",
        },
        "manual-09-cflib": {
            "<p>可以看到，我们在第10行导入了cflib中的motioncommander模块，我们将调用该模块的功能使得无人机进行飞行，详细的类函数，有余力的同学可以进入该网址查看：github.com</p>":
            "<p>可以看到，我们在第10行导入了cflib中的motioncommander模块，我们将调用该模块的功能使得无人机进行飞行。详细的类函数可查看course-materials中的源码：<code>course-materials/05_source_references/crazyflie-lib-python-master.zip</code>。</p>",
            "<p>As you can see, we imported the motioncommander module in cflib on line 10. We will call the function of this module to make the drone fly. For detailed class functions, students who have spare capacity can go to this website to view: github.com</p>":
            "<p>As you can see, we imported the motioncommander module in cflib on line 10. We will call this module to fly the drone. For detailed class functions, refer to the source archive in the Course Materials Package: <code>course-materials/05_source_references/crazyflie-lib-python-master.zip</code>.</p>",
        },
    }
    for old, new in common_pairs.items():
        body = body.replace(old, new)
    for old, new in manual_pairs.get(manual.slug, {}).items():
        body = body.replace(old, new)
    if manual.slug in {"manual-05-ranging", "manual-06-complex-map"}:
        body = apply_wall_following_examples(manual, lang, body)
    return body


def vm_manual_supplement(lang: str) -> str:
    if lang == "zh":
        return '''<h3>Mac 用户补充方案</h3>
<p>Intel Mac 用户可以继续使用本实验主流程中的 amd64 Ubuntu 20.04 Desktop 镜像，只需将虚拟机软件替换为 VMware Fusion、UTM 或 VirtualBox 等 macOS 可用工具。</p>
<p>Apple Silicon Mac（M1/M2/M3/M4）不能直接使用 amd64 桌面镜像，应使用 ARM64 Ubuntu 虚拟机。ARM64 镜像地址：</p>
<pre><code>https://cdimage.ubuntu.com/ubuntu/releases/20.04.5/release/ubuntu-20.04.5-live-server-arm64.iso</code></pre>
<p>该镜像是 Ubuntu Server，默认没有图形界面。使用 VMware Fusion 创建虚拟机并启动后，按文本安装界面完成以下配置：语言选择 English，键盘保持 English (US)，网络使用 DHCP，镜像源保持默认，磁盘选择 <code>Use an entire disk</code>，创建用户名、主机名和密码；OpenSSH 可按需要勾选，其他附加软件包暂不选择。安装完成后选择 <code>Reboot Now</code>，如提示移除安装介质，请在虚拟机设置中断开 ISO 后回车继续。</p>
<p>首次登录命令行后，执行以下命令安装桌面环境和 VMware 工具：</p>
<pre><code>sudo apt update
sudo apt install -y ubuntu-desktop open-vm-tools open-vm-tools-desktop
sudo reboot</code></pre>
<div class="admonition warning"><p class="admonition-title">课堂建议</p><p>Apple Silicon 方案应作为补充方案使用，并在正式实验前完成 ROS Noetic、cfclient、课程仿真工程和 Crazyradio USB 透传测试。课堂主方案仍建议使用 x86_64 Ubuntu 20.04 Desktop 虚拟机，以保证环境一致。</p></div>
'''
    return '''<h3>Supplement for Mac Users</h3>
<p>Intel Mac users can continue to use the amd64 Ubuntu 20.04 Desktop image in the main workflow. Replace VMware Workstation with a macOS virtualization tool such as VMware Fusion, UTM, or VirtualBox.</p>
<p>Apple Silicon Macs (M1/M2/M3/M4) should not use the amd64 desktop image directly. Use an ARM64 Ubuntu virtual machine instead. ARM64 image URL:</p>
<pre><code>https://cdimage.ubuntu.com/ubuntu/releases/20.04.5/release/ubuntu-20.04.5-live-server-arm64.iso</code></pre>
<p>This image is Ubuntu Server and does not include a desktop environment by default. After creating and starting the virtual machine in VMware Fusion, complete the text-mode installer as follows: select English, keep the keyboard as English (US), use DHCP networking, keep the default mirror, select <code>Use an entire disk</code>, and create the username, host name, and password. OpenSSH is optional; leave other extra package selections empty. After installation, choose <code>Reboot Now</code>. If the installer asks you to remove the installation medium, disconnect the ISO in the virtual-machine settings and press Enter.</p>
<p>After the first command-line login, install the desktop environment and VMware tools:</p>
<pre><code>sudo apt update
sudo apt install -y ubuntu-desktop open-vm-tools open-vm-tools-desktop
sudo reboot</code></pre>
<div class="admonition warning"><p class="admonition-title">Classroom note</p><p>Treat the Apple Silicon path as a supplemental path and verify ROS Noetic, cfclient, the course simulation project, and Crazyradio USB passthrough before the formal lab. The primary classroom path should remain an x86_64 Ubuntu 20.04 Desktop VM so that the environment stays consistent.</p></div>
'''


def apply_vm_manual_overrides(lang: str, body: str) -> str:
    if lang == "zh":
        marker = '<h2>三、实验步骤</h2>'
        sentinel = "Mac 用户补充方案"
        replacements = {
            "<p>物理机配置：建议8GB以上内存、50GB以上可用磁盘空间（虚拟机需占用约20GB）。</p>":
            "<p>物理机配置：建议16GB以上内存，并保证能够为虚拟机分配100GB磁盘空间。虚拟机统一按8GB内存、100GB磁盘配置，后续扩展实验也优先复用该环境。</p>",
            "<p>运行内存可以使用默认推荐内存，点击下一步</p>":
            "<p>运行内存设置为8GB，设置完成后点击下一步</p>",
            "<p>可以稍微增大磁盘空间，点击下一步</p>":
            "<p>磁盘容量设置为100GB，后续实验会继续使用该虚拟机环境。设置完成后点击下一步</p>",
            "<p>处理器：根据物理机核心数分配（如4核CPU分配2核，每个核心1-2线程）。</p>":
            "<p>处理器：根据物理机核心数分配，建议至少分配4个虚拟CPU；高性能电脑可分配6-8个虚拟CPU，但应保留足够资源给宿主机。</p>",
            "<p>基础任务：2GB</p>":
            "<p>统一配置：8GB</p>",
            "<p>多任务/开发环境：4GB</p>":
            "",
            "<p>保留至少4GB内存给物理机。</p>":
            "<p>保留至少8GB内存给物理机。</p>",
            "<p>容量：分配60GB，选择“存储为单个文件”。</p>":
            "<p>容量：分配100GB，选择“存储为单个文件”。</p>",
            "<p>/（根目录）：20GB，EXT4文件系统。</p>":
            "<p>/（根目录）：50GB，EXT4文件系统。</p>",
            "<p>Swap（交换分区）：2GB（内存不足时备用）。</p>":
            "<p>Swap（交换分区）：4GB（内存不足时备用）。</p>",
        }
    else:
        marker = '<h2>3. Experimental steps</h2>'
        sentinel = "Supplement for Mac Users"
        replacements = {
            "<p>Physical machine configuration: It is recommended to have more than 8GB of memory and more than 50GB of available disk space (the virtual machine needs to occupy about 20GB).</p>":
            "<p>Physical machine configuration: more than 16GB of memory is recommended, and the host should be able to allocate a 100GB virtual disk. Configure the virtual machine with 8GB of memory and a 100GB disk; the same environment should be reused for later extended experiments whenever possible.</p>",
            "<p>You can use the default recommended memory for running memory, click Next</p>":
            "<p>Set the virtual-machine memory to 8GB, then click Next.</p>",
            "<p>You can slightly increase the disk space, click Next</p>":
            "<p>Set the disk capacity to 100GB. Later experiments will continue to use this virtual-machine environment. Then click Next.</p>",
            "<p>Processor: allocated according to the number of cores of the physical machine (for example, a 4-core CPU is allocated 2 cores, and each core has 1-2 threads).</p>":
            "<p>Processor: allocate resources according to the number of host CPU cores. At least 4 virtual CPUs are recommended. High-performance computers may use 6-8 virtual CPUs, while keeping enough resources for the host system.</p>",
            "<p>Basic tasks: 2GB</p>":
            "<p>Unified configuration: 8GB</p>",
            "<p>Multitasking/development environment: 4GB</p>":
            "",
            "<p>Reserve at least 4GB of memory for the physical machine.</p>":
            "<p>Reserve at least 8GB of memory for the host machine.</p>",
            "<p>Capacity: Allocate 60GB, select &quot;Store as single file&quot;.</p>":
            "<p>Capacity: allocate 100GB and select &quot;Store as single file&quot;.</p>",
            "<p>/ (root directory): 20GB, EXT4 file system.</p>":
            "<p>/ (root directory): 50GB, EXT4 file system.</p>",
            "<p>Swap (swap partition): 2GB (spare when memory is insufficient).</p>":
            "<p>Swap (swap partition): 4GB (spare when memory is insufficient).</p>",
        }
    for old, new in replacements.items():
        body = body.replace(old, new)
    if sentinel not in body and marker in body:
        body = body.replace(marker, vm_manual_supplement(lang) + marker, 1)
    return body


def apply_cflib_copyable_code_overrides(lang: str, body: str) -> str:
    takeoff_program = """import logging
import sys
import time
from threading import Event

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper

URI = uri_helper.uri_from_env(default='radio://0/80/2M/E7E7E7E7E7')
DEFAULT_HEIGHT = 0.5
deck_attached_event = Event()

logging.basicConfig(level=logging.ERROR)


def param_deck_flow(_, value_str):
    value = int(value_str)
    print(value)
    if value:
        deck_attached_event.set()
        print('Deck is attached!')
    else:
        print('Deck is NOT attached!')


def take_off_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(3)
        mc.stop()


if __name__ == '__main__':
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        scf.cf.param.add_update_callback(
            group='deck',
            name='bcFlow2',
            cb=param_deck_flow,
        )
        time.sleep(1)

        if not deck_attached_event.wait(timeout=5):
            print('No flow deck detected!')
            sys.exit(1)

        scf.cf.platform.send_arming_request(True)
        time.sleep(1.0)
        take_off_simple(scf)"""
    forward_back_function = """def move_linear_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)
        mc.back(0.5)
        time.sleep(1)"""
    turn_function = """def move_linear_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)
        mc.turn_left(180)
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)"""

    code_blocks = {
        6: f"<pre><code>{html.escape(takeoff_program)}</code></pre>",
        7: f"<pre><code>{html.escape(forward_back_function)}</code></pre>",
        8: f"<pre><code>{html.escape(turn_function)}</code></pre>",
    }
    for index in (2, 4, 5, 9):
        pattern = rf'<figure><img src="\.\./assets/(?:images|images-en)/manual-09-cflib/{index:03d}\.png" alt="manual image" loading="lazy" decoding="async"></figure>'
        body = re.sub(pattern, "", body)
    for index, replacement in code_blocks.items():
        pattern = rf'<figure><img src="\.\./assets/(?:images|images-en)/manual-09-cflib/{index:03d}\.png" alt="manual image" loading="lazy" decoding="async"></figure>'
        body = re.sub(pattern, replacement, body)

    if lang == "zh":
        paragraph_replacements = {
            "<p>将已有的程序按照如下图所示的程序进行编写。（之前的param_deck_flow函数可以保留），然后运行该程序，无人机将会起飞悬停3秒后降落。第21至23行则会控制该飞行流程，第14行设置了默认起飞高度。可以适当改变这些参数来观察效果。</p>":
            "<p>将 <code>motion_flying.py</code> 改为下面的完整可复制版本。运行后，无人机将起飞并悬停 3 秒，然后自动降落。<code>DEFAULT_HEIGHT</code> 设置默认起飞高度；首次测试时应保持低高度，并确认急停方式。</p>",
            "<p>我们再在主函数前添加以下函数，将程序最后一行要调用的函数替换为该函数。（例如将刚才在上图42行调用的take_off_simple函数替换为现在的move_linear_simple函数）。该函数的作用为无人机起飞之后，悬停一秒，前进0.5米，再悬停一秒，后退0.5米，再悬停一秒，随后降落。我们通过motioncommander类实体化一个对象mc，通过调用mc的成员函数forward和back实现无人机的前进后退。</p>":
            "<p>在主函数前添加下面的 <code>move_linear_simple</code> 函数，并将主函数最后调用的 <code>take_off_simple(scf)</code> 改为 <code>move_linear_simple(scf)</code>。无人机起飞后将悬停 1 秒、前进 0.5 米、再次悬停 1 秒、后退 0.5 米，随后降落。</p>",
            "<p>再进一步地，我们将函数的内容替换为如下：</p>":
            "<p>如果需要演示转向后返回，将 <code>move_linear_simple</code> 替换为下面的可复制版本：</p>",
            "<p>根据我们学习到的在终端中打印出无人机在实时运行时的飞行数据，参照如下代码（take_off_simple(scf)函数和param_deck_flow(name, value_str)函数可以保留，也可以如下所示无内容）：</p>":
            "<p>下面给出记录实时位置数据的完整可复制程序。其中 <code>log_pos_callback</code> 更新位置估计，<code>param_deck_flow</code> 检查 Flow deck 是否已连接。</p>",
            "<p>再新定义加入一个名字为move_box_limit的函数，放在主函数中，同样地参考程序如下：</p>":
            "<p>下面给出包含 <code>move_box_limit</code> 的完整可复制程序。运行前请确认位置日志能够正常更新，并由一名组员负责急停。</p>",
        }
    else:
        paragraph_replacements = {
            "<p>Write the existing program as shown in the figure below. (The previous param_deck_flow function can be retained), then run the program, the drone will take off and hover for 3 seconds before landing. Lines 21 to 23 will control the flight process, and line 14 sets the default takeoff altitude. These parameters can be changed appropriately to observe the effect.</p>":
            "<p>Replace <code>motion_flying.py</code> with the complete copyable version below. The drone takes off, hovers for 3 seconds, and then lands automatically. <code>DEFAULT_HEIGHT</code> sets the default takeoff height; keep it low for the first test and confirm the emergency-stop procedure.</p>",
            "<p>We then add the following function before the main function and replace the function to be called in the last line of the program with this function. (For example, replace the take_off_simple function just called in line 42 of the figure above with the current move_linear_simple function). The function of this function is that after the drone takes off, it hovers for one second, moves forward 0.5 meters, hovers for another second, retreats 0.5 meters, hovers for another second, and then lands. We materialize an object mc through the motioncommander class, and realize the forward and backward movement of the drone by calling the member functions forward and back of mc.</p>":
            "<p>Add the copyable <code>move_linear_simple</code> function below before the main function, and replace the final <code>take_off_simple(scf)</code> call with <code>move_linear_simple(scf)</code>. After takeoff, the drone hovers for 1 second, moves forward 0.5 m, hovers again, moves back 0.5 m, and then lands.</p>",
            "<p>Going a step further, we replace the content of the function with the following:</p>":
            "<p>To demonstrate turning and returning, replace <code>move_linear_simple</code> with the copyable version below:</p>",
            "<p>According to what we have learned about printing the flight data of the drone in real-time operation in the terminal, refer to the following code (the take_off_simple(scf) function and the param_deck_flow(name, value_str) function can be retained or have no content as shown below):</p>":
            "<p>The complete copyable program below records live position data. <code>log_pos_callback</code> updates the position estimate, while <code>param_deck_flow</code> checks whether the Flow deck is connected.</p>",
            "<p>Define and add a new function named move_box_limit, put it in the main function, and refer to the program as follows:</p>":
            "<p>The complete copyable program below includes <code>move_box_limit</code>. Before running it, confirm that position logging updates correctly and assign one team member to emergency-stop duty.</p>",
            "<p>Then redefine and add a function named move_box_limit and place it in the main function. The same reference program is as follows:</p>":
            "<p>The complete copyable program below includes <code>move_box_limit</code>. Before running it, confirm that position logging updates correctly and assign one team member to emergency-stop duty.</p>",
        }
    for old_text, new_text in paragraph_replacements.items():
        body = body.replace(old_text, new_text)
    return body


def apply_manual_overrides(manual: Manual, lang: str, body: str) -> str:
    if manual.slug == "manual-01-vm":
        return apply_vm_manual_overrides(lang, body)
    if manual.slug == "manual-09-cflib":
        return apply_cflib_copyable_code_overrides(lang, body)
    if manual.slug != "manual-03-crazyflie-setup":
        return body
    if lang == "zh":
        cleanup_pairs = {
            "<h3>实验一：将cfclient的软件安装包拷贝到虚拟机的workspace文件夹中进行安装步骤</h3>": "<h3>实验一：使用 Git 获取 cfclient 指定版本并安装</h3>",
            "<p>此时再点击绿色的extract按键</p>": "",
            "<p>点击进入解压好的目录中，右键界面空白处选择open in terminal呼出终端。</p>": "",
        }
        image_root = "images"
    else:
        cleanup_pairs = {
            "<h3>Experiment 1: Copy the cfclient software installation package to the workspace folder of the virtual machine and proceed with the installation steps.</h3>": "<h3>Experiment 1: Use Git to obtain the specified cfclient version and install it</h3>",
            "<p>At this point click the green extract button</p>": "",
            "<p>Click to enter the decompressed directory, right-click on a blank space on the interface and select open in terminal to call out the terminal.</p>": "",
        }
        image_root = "images-en"
    for old_text, new_text in cleanup_pairs.items():
        body = body.replace(old_text, new_text)
    for index in range(1, 5):
        figure = f'<figure><img src="../assets/{image_root}/manual-03-crazyflie-setup/{index:03d}.png" alt="manual image" loading="lazy" decoding="async"></figure>'
        body = body.replace(figure, "")
    image = '<figure><img src="../assets/images/manual-03-crazyflie-setup/009.png" alt="manual image" loading="lazy" decoding="async"></figure>'
    if lang == "zh":
        old = f'''<p>\u518d\u8f93\u5165\u4ee5\u4e0b\u547d\u4ee4\u66f4\u65b0\u8f6f\u4ef6\u5de5\u5177\uff1a</p>
<p>pip3 install --upgrade pip setuptools wheel</p>
{image}
<p>\u6700\u540e\u8f93\u5165\u4ee5\u4e0b\u547d\u4ee4\u8fdb\u884c\u603b\u7684\u8f6f\u4ef6\u4f9d\u8d56\u5b89\u88c5\u6574\u7406\uff1a</p>
<pre><code>pip3 install -e .</code></pre>'''
        new = f'''<p>\u518d\u8f93\u5165\u4ee5\u4e0b\u547d\u4ee4\u66f4\u65b0 Python \u6253\u5305\u5de5\u5177\u3002Ubuntu 20.04 \u7684 Python 3.8 \u73af\u5883\u4e2d\uff0c\u76f4\u63a5\u5347\u7ea7\u5230\u6700\u65b0 <code>setuptools</code> \u53ef\u80fd\u4e0e\u65e7\u7248 <code>importlib_metadata</code> \u51b2\u7a81\uff0c\u5e76\u5728\u540e\u7eed\u5b89\u88c5\u65f6\u51fa\u73b0 <code>AttributeError: module &#x27;importlib_metadata&#x27; has no attribute &#x27;EntryPoints&#x27;</code>\u3002\u56e0\u6b64\u8fd9\u91cc\u56fa\u5b9a <code>setuptools</code> \u5230 71 \u4ee5\u4e0b\uff0c\u5e76\u8865\u9f50 <code>importlib_metadata</code> \u548c <code>testresources</code>\u3002</p>
<pre><code>python3 -m pip install --user --upgrade pip wheel importlib_metadata testresources
python3 -m pip install --user --upgrade &quot;setuptools&lt;71&quot;</code></pre>
{image}
<div class="admonition warning"><p class="admonition-title">\u6545\u969c\u5904\u7406</p><p>\u5982\u679c\u5df2\u7ecf\u6267\u884c\u8fc7\u65e7\u547d\u4ee4\uff0c\u5e76\u5728 <code>pip3 install -e .</code> \u65f6\u770b\u5230\u4e0a\u8ff0 <code>EntryPoints</code> \u62a5\u9519\uff0c\u5148\u6267\u884c\u4e0a\u9762\u7684\u4e24\u884c\u5de5\u5177\u4fee\u590d\u547d\u4ee4\uff0c\u518d\u56de\u5230 <code>crazyflie-clients-python</code> \u76ee\u5f55\u7ee7\u7eed\u6267\u884c\u4e0b\u9762\u7684\u5b89\u88c5\u547d\u4ee4\u3002</p></div>
<p>\u6700\u540e\u8f93\u5165\u4ee5\u4e0b\u547d\u4ee4\u8fdb\u884c\u603b\u7684\u8f6f\u4ef6\u4f9d\u8d56\u5b89\u88c5\u6574\u7406\uff1a</p>
<pre><code>python3 -m pip install --user -e .</code></pre>'''
        body = body.replace(old, new)
        marker = '<h3>\u5b9e\u9a8c\u56db\uff1a\u4f7f\u7528python\u811a\u672c\u8ba9\u65e0\u4eba\u673a\u81ea\u4e3b\u8d77\u98de</h3>'
        radio_section = '''<h3>\u591a\u7ec4\u540c\u65f6\u5b9e\u9a8c\u7684\u65e0\u7ebf\u9891\u6bb5\u89c4\u5212</h3>
<p>\u6b63\u5f0f\u5b9e\u9a8c\u4e2d\u5982\u679c 12 \u7ec4\u5728\u540c\u4e00\u623f\u95f4\u540c\u65f6\u4f7f\u7528 Crazyradio\uff0c\u5efa\u8bae\u4e3a\u6bcf\u7ec4\u56fa\u5b9a\u4e00\u5957\u5b8c\u6574\u7684 radio URI\u3002URI \u683c\u5f0f\u4e3a <code>radio://\u63a5\u53e3\u7f16\u53f7/\u4fe1\u9053/\u901f\u7387/\u5730\u5740</code>\uff0c\u4f8b\u5982 <code>radio://0/60/2M/E7E7E7E7A6</code>\u3002\u5176\u4e2d\uff0c\u4fe1\u9053\u7528\u4e8e\u51cf\u5c11\u540c\u9891\u65e0\u7ebf\u62e5\u585e\uff0c\u5730\u5740\u7528\u4e8e\u907f\u514d\u8bef\u8fde\u5230\u5176\u4ed6\u7ec4\u7684\u65e0\u4eba\u673a\uff1b\u53ea\u4fee\u6539\u5730\u5740\u4e0d\u80fd\u5b8c\u5168\u89e3\u51b3\u540c\u9891\u5e72\u6270\u95ee\u9898\u3002</p>
<table><tbody>
<tr><th>\u7ec4\u522b</th><th>Channel</th><th>Address</th><th>\u5b8c\u6574 URI</th></tr>
<tr><td>1\u7ec4 / A\u7ec4</td><td>10</td><td><code>E7E7E7E7A1</code></td><td><code>radio://0/10/2M/E7E7E7E7A1</code></td></tr>
<tr><td>2\u7ec4 / B\u7ec4</td><td>20</td><td><code>E7E7E7E7A2</code></td><td><code>radio://0/20/2M/E7E7E7E7A2</code></td></tr>
<tr><td>3\u7ec4 / C\u7ec4</td><td>30</td><td><code>E7E7E7E7A3</code></td><td><code>radio://0/30/2M/E7E7E7E7A3</code></td></tr>
<tr><td>4\u7ec4 / D\u7ec4</td><td>40</td><td><code>E7E7E7E7A4</code></td><td><code>radio://0/40/2M/E7E7E7E7A4</code></td></tr>
<tr><td>5\u7ec4 / E\u7ec4</td><td>50</td><td><code>E7E7E7E7A5</code></td><td><code>radio://0/50/2M/E7E7E7E7A5</code></td></tr>
<tr><td>6\u7ec4 / F\u7ec4</td><td>60</td><td><code>E7E7E7E7A6</code></td><td><code>radio://0/60/2M/E7E7E7E7A6</code></td></tr>
<tr><td>7\u7ec4 / G\u7ec4</td><td>70</td><td><code>E7E7E7E7A7</code></td><td><code>radio://0/70/2M/E7E7E7E7A7</code></td></tr>
<tr><td>8\u7ec4 / H\u7ec4</td><td>80</td><td><code>E7E7E7E7A8</code></td><td><code>radio://0/80/2M/E7E7E7E7A8</code></td></tr>
<tr><td>9\u7ec4 / I\u7ec4</td><td>90</td><td><code>E7E7E7E7A9</code></td><td><code>radio://0/90/2M/E7E7E7E7A9</code></td></tr>
<tr><td>10\u7ec4 / J\u7ec4</td><td>100</td><td><code>E7E7E7E7AA</code></td><td><code>radio://0/100/2M/E7E7E7E7AA</code></td></tr>
<tr><td>11\u7ec4 / K\u7ec4</td><td>110</td><td><code>E7E7E7E7AB</code></td><td><code>radio://0/110/2M/E7E7E7E7AB</code></td></tr>
<tr><td>12\u7ec4 / L\u7ec4</td><td>120</td><td><code>E7E7E7E7AC</code></td><td><code>radio://0/120/2M/E7E7E7E7AC</code></td></tr>
</tbody></table>
<p>\u914d\u7f6e\u65f6\u5148\u7528 USB \u5355\u72ec\u8fde\u63a5\u4e00\u67b6\u65e0\u4eba\u673a\uff0c\u5728 cfclient \u4e2d\u8fde\u63a5 <code>usb://0</code>\uff0c\u8fdb\u5165 <code>Connect - Configure 2.x</code>\uff0c\u5199\u5165\u8be5\u7ec4\u5206\u914d\u7684 Radio channel \u548c Radio address\uff0c\u4fdd\u5b58\u540e\u91cd\u542f\u65e0\u4eba\u673a\u3002\u4e4b\u540e\u8be5\u7ec4\u7684 cfclient \u5730\u5740\u680f\u548c\u6240\u6709 Python \u811a\u672c\u90fd\u5e94\u4f7f\u7528\u540c\u4e00\u4e2a\u5b8c\u6574 URI\u3002</p>
<div class="admonition warning"><p class="admonition-title">\u8bfe\u5802\u6ce8\u610f\u4e8b\u9879</p><p>\u540c\u4e00\u623f\u95f4\u591a\u7ec4\u5b9e\u9a8c\u65f6\uff0c\u4fe1\u9053\u5c3d\u91cf\u62c9\u5f00\uff0c\u4f8b\u5982\u95f4\u9694 10\uff1b\u6bcf\u67b6\u65e0\u4eba\u673a\u548c\u6bcf\u53f0\u7535\u8111\u65c1\u5e94\u8d34\u4e0a\u7ec4\u522b\u3001channel\u3001address \u548c\u5b8c\u6574 URI\u3002\u6b63\u5f0f\u98de\u884c\u524d\u5148\u9010\u7ec4\u5355\u72ec\u6d4b\u8bd5\u8fde\u63a5\uff0c\u786e\u8ba4\u4e0d\u4f1a\u626b\u63cf\u6216\u8fde\u63a5\u5230\u5176\u4ed6\u7ec4\u65e0\u4eba\u673a\u3002</p></div>
'''
        if "radio://0/120/2M/E7E7E7E7AC" not in body:
            body = body.replace(marker, radio_section + marker)
        return body
    old = f'''<p>Then enter the following command to update the software tool:</p>
<p>pip3 install --upgrade pip setuptools wheel</p>
{image}
<p>Finally, enter the following command to complete the overall software dependency installation:</p>
<pre><code>pip3 install -e .</code></pre>'''
    new = f'''<p>Then update the Python packaging tools. In Ubuntu 20.04 with Python 3.8, upgrading directly to the newest <code>setuptools</code> can conflict with an older <code>importlib_metadata</code> package and later cause <code>AttributeError: module &#x27;importlib_metadata&#x27; has no attribute &#x27;EntryPoints&#x27;</code>. Keep <code>setuptools</code> below 71 and install <code>importlib_metadata</code> and <code>testresources</code> explicitly.</p>
<pre><code>python3 -m pip install --user --upgrade pip wheel importlib_metadata testresources
python3 -m pip install --user --upgrade &quot;setuptools&lt;71&quot;</code></pre>
{image}
<div class="admonition warning"><p class="admonition-title">Troubleshooting</p><p>If you already ran the old command and see the <code>EntryPoints</code> error during <code>pip3 install -e .</code>, run the two tool-fix commands above first. Then return to the <code>crazyflie-clients-python</code> directory and continue with the installation command below.</p></div>
<p>Finally, enter the following command to complete the overall software dependency installation:</p>
<pre><code>python3 -m pip install --user -e .</code></pre>'''
    body = body.replace(old, new)
    marker = '<h3>Experiment 4: Use python script to make drone take off autonomously</h3>'
    radio_section = '''<h3>Radio Planning for Multi-group Experiments</h3>
<p>When 12 groups use Crazyradio in the same room, assign each group a fixed complete radio URI. The URI format is <code>radio://interface/channel/data-rate/address</code>, for example <code>radio://0/60/2M/E7E7E7E7A6</code>. The channel reduces same-frequency congestion, while the address prevents accidental connection to another group&apos;s drone. Changing only the address is not enough to fully avoid same-channel interference.</p>
<table><tbody>
<tr><th>Group</th><th>Channel</th><th>Address</th><th>Complete URI</th></tr>
<tr><td>Group 1 / A</td><td>10</td><td><code>E7E7E7E7A1</code></td><td><code>radio://0/10/2M/E7E7E7E7A1</code></td></tr>
<tr><td>Group 2 / B</td><td>20</td><td><code>E7E7E7E7A2</code></td><td><code>radio://0/20/2M/E7E7E7E7A2</code></td></tr>
<tr><td>Group 3 / C</td><td>30</td><td><code>E7E7E7E7A3</code></td><td><code>radio://0/30/2M/E7E7E7E7A3</code></td></tr>
<tr><td>Group 4 / D</td><td>40</td><td><code>E7E7E7E7A4</code></td><td><code>radio://0/40/2M/E7E7E7E7A4</code></td></tr>
<tr><td>Group 5 / E</td><td>50</td><td><code>E7E7E7E7A5</code></td><td><code>radio://0/50/2M/E7E7E7E7A5</code></td></tr>
<tr><td>Group 6 / F</td><td>60</td><td><code>E7E7E7E7A6</code></td><td><code>radio://0/60/2M/E7E7E7E7A6</code></td></tr>
<tr><td>Group 7 / G</td><td>70</td><td><code>E7E7E7E7A7</code></td><td><code>radio://0/70/2M/E7E7E7E7A7</code></td></tr>
<tr><td>Group 8 / H</td><td>80</td><td><code>E7E7E7E7A8</code></td><td><code>radio://0/80/2M/E7E7E7E7A8</code></td></tr>
<tr><td>Group 9 / I</td><td>90</td><td><code>E7E7E7E7A9</code></td><td><code>radio://0/90/2M/E7E7E7E7A9</code></td></tr>
<tr><td>Group 10 / J</td><td>100</td><td><code>E7E7E7E7AA</code></td><td><code>radio://0/100/2M/E7E7E7E7AA</code></td></tr>
<tr><td>Group 11 / K</td><td>110</td><td><code>E7E7E7E7AB</code></td><td><code>radio://0/110/2M/E7E7E7E7AB</code></td></tr>
<tr><td>Group 12 / L</td><td>120</td><td><code>E7E7E7E7AC</code></td><td><code>radio://0/120/2M/E7E7E7E7AC</code></td></tr>
</tbody></table>
<p>To configure a drone, connect one Crazyflie by USB, connect to <code>usb://0</code> in cfclient, open <code>Connect - Configure 2.x</code>, write the assigned Radio channel and Radio address, save the settings, and restart the drone. After that, the cfclient address field and all Python scripts for that group should use the same complete URI.</p>
<div class="admonition warning"><p class="admonition-title">Classroom note</p><p>For multi-group experiments in one room, keep channels well separated, for example by 10 channels. Label each drone and computer with its group, channel, address, and full URI. Before formal flight, test each group one by one and confirm that it does not scan or connect to another group&apos;s drone.</p></div>
'''
    if "Radio Planning for Multi-group Experiments" not in body:
        body = body.replace(marker, radio_section + marker)
    return body


def demo_material_image_src(slug: str, item: dict[str, str], lang: str) -> str:
    image_root = "images-en" if lang == "en" else "images"
    return f"../assets/{image_root}/{slug}/{item['name']}"


def demo_material_section(manual: Manual, lang: str) -> str:
    items = DEMO_MATERIALS.get(manual.slug)
    if not items:
        return ""
    section_meta = {
        "manual-04-multiranger": {
            "zh_heading": "现场测试场地",
            "en_heading": "On-site Test Setup",
            "zh_intro": "本场地用于验证 Multi-ranger 各方向测距读数与挡板相对位置之间的对应关系。",
            "en_intro": "This setup is used to verify the correspondence between Multi-ranger readings and the relative positions of the baffles.",
        },
        "manual-06-complex-map": {
            "zh_heading": "建图结果参考",
            "en_heading": "Mapping Result Reference",
            "zh_intro": "复盘建图实验时，可将现场场地结构与点云输出进行对照，重点检查外边界、内部挡板和异常散点。",
            "en_intro": "When reviewing the mapping experiment, compare the physical arena structure with the point-cloud output, focusing on the outer boundary, internal baffles, and abnormal scattered points.",
        },
        "manual-11-integrated-practice": {
            "zh_heading": "综合路线场地参考",
            "en_heading": "Integrated Route Arena Reference",
            "zh_intro": "路线复盘时应将任务拆分为若干连续动作段，分别检查每一段的控制结果和误差来源。",
            "en_intro": "During route review, split the task into continuous action segments and check the control result and error source of each segment.",
        },
        "manual-13-project-demo": {
            "zh_heading": "比赛场地记录",
            "en_heading": "Competition Arena Record",
            "zh_intro": "比赛评价应结合现场飞行、终端日志和影像记录，核对关键通行点与安全边界。",
            "en_intro": "Competition evaluation should combine on-site flight, terminal logs, and visual records to check key passing points and safety boundaries.",
        },
    }
    meta = section_meta.get(manual.slug, {})
    if lang == "zh":
        heading = meta.get("zh_heading", "现场记录")
        intro = meta.get("zh_intro", "")
        title_key = "zh_title"
        text_key = "zh_text"
    else:
        heading = meta.get("en_heading", "On-site Record")
        intro = meta.get("en_intro", "")
        title_key = "en_title"
        text_key = "en_text"
    figures: list[str] = []
    for item in items:
        title = item[title_key]
        description = item[text_key]
        src = demo_material_image_src(manual.slug, item, lang)
        figures.append(
            f'<figure class="demo-figure"><img src="{html.escape(src)}" alt="{html.escape(title)}" loading="lazy" decoding="async">'
            f'<figcaption><strong>{html.escape(title)}</strong><span>{html.escape(description)}</span></figcaption></figure>'
        )
    intro_html = f"<p>{html.escape(intro)}</p>\n" if intro else ""
    heading_html = f"\n<h2>{html.escape(heading)}</h2>\n"
    return heading_html + intro_html + "\n".join(figures)

def demo_video_src(slug: str, item: dict[str, str]) -> str:
    return f"../assets/videos/{slug}/{item['name']}"


def demo_video_section(manual: Manual, lang: str) -> str:
    items = DEMO_VIDEOS.get(manual.slug)
    if not items:
        return ""
    section_meta = {
        "manual-05-ranging": {
            "zh_heading": "飞行记录参考",
            "en_heading": "Flight Record Reference",
            "zh_intro": "复盘测距进阶实验时，应将飞行动作、测距阈值和安全边界一并核对。",
            "en_intro": "When reviewing the advanced ranging experiment, check flight actions, ranging thresholds, and safety boundaries together.",
        },
        "manual-06-complex-map": {
            "zh_heading": "飞行过程记录",
            "en_heading": "Flight Process Record",
            "zh_intro": "飞行视频用于记录采样路径与障碍关系，便于与建图结果交叉核验。",
            "en_intro": "The flight video records the relationship between the sampling path and obstacles, so it can be cross-checked with the mapping result.",
        },
        "manual-13-project-demo": {
            "zh_heading": "综合任务飞行记录",
            "en_heading": "Integrated-task Flight Record",
            "zh_intro": "视频记录用于核对路线完成情况、安全边界和评分依据。",
            "en_intro": "The video record is used to check route completion, safety boundaries, and scoring evidence.",
        },
    }
    meta = section_meta.get(manual.slug, {})
    if lang == "zh":
        heading = meta.get("zh_heading", "飞行记录")
        intro = meta.get("zh_intro", "")
        title_key = "zh_title"
        text_key = "zh_text"
    else:
        heading = meta.get("en_heading", "Flight Record")
        intro = meta.get("en_intro", "")
        title_key = "en_title"
        text_key = "en_text"
    figures: list[str] = []
    for item in items:
        title = item[title_key]
        description = item[text_key]
        src = demo_video_src(manual.slug, item)
        figures.append(
            f'<figure class="demo-video"><video controls muted playsinline preload="metadata">'
            f'<source src="{html.escape(src)}" type="video/mp4"></video>'
            f'<figcaption><strong>{html.escape(title)}</strong><span>{html.escape(description)}</span></figcaption></figure>'
        )
    intro_html = f"<p>{html.escape(intro)}</p>\n" if intro else ""
    heading_html = f"\n<h2>{html.escape(heading)}</h2>\n"
    return heading_html + intro_html + "\n".join(figures)


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
        manifest[manual.slug] = {**stats, "videos": 0}
        translation_texts.update(collect_translation_texts(blocks))

    image_ocr = collect_image_ocr(extracted)
    translation_texts.update(collect_image_translation_texts(image_ocr))
    cache = ensure_translations(translation_texts)
    image_map = build_english_images(image_ocr, cache)
    copy_final_test_images()
    copy_cfclient_toolchain_image()
    copy_demo_material_images()
    copy_demo_videos()
    for slug, items in DEMO_MATERIALS.items():
        if slug in manifest:
            manifest[slug]["images"] += len(items)
    for slug, items in DEMO_VIDEOS.items():
        if slug in manifest:
            manifest[slug]["videos"] += len(items)

    for manual, blocks, _stats in extracted.values():
        if manual.slug == FINAL_TEST_SLUG:
            zh_body = '<h1>\u6bd4\u8d5b\u8bf4\u660e\uff1a\u7efc\u5408\u9879\u76ee\u5c55\u793a\u4efb\u52a1</h1><p class="subtitle">Integrated Project Competition</p>' + render_blocks(blocks, "zh", cache)
            en_body = '<h1>Competition Brief: Integrated Project Competition</h1>' + render_blocks(blocks, "en", cache, image_map)
        else:
            zh_body = f'<h1>\u5b9e\u9a8c {manual.number}: {html.escape(manual.zh_title)}</h1><p class="subtitle">{html.escape(manual.en_title)}</p>' + render_blocks(blocks, "zh", cache)
            en_body = english_body(manual, blocks, cache, image_map)
        zh_body = apply_course_material_overrides(manual, "zh", zh_body)
        en_body = apply_course_material_overrides(manual, "en", en_body)
        zh_body = apply_manual_overrides(manual, "zh", zh_body)
        en_body = apply_manual_overrides(manual, "en", en_body)
        zh_body = apply_course_material_overrides(manual, "zh", zh_body)
        en_body = apply_course_material_overrides(manual, "en", en_body)
        zh_body += demo_material_section(manual, "zh")
        en_body += demo_material_section(manual, "en")
        zh_body += demo_video_section(manual, "zh")
        en_body += demo_video_section(manual, "en")
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
.nav-group{margin:16px 20px 6px;color:#55a5d9;font-size:12px;font-weight:700;text-transform:uppercase}
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
pre.has-copy-button{position:relative;padding-top:48px}
pre code{display:block;border:0;padding:0;background:transparent;font-size:14px;white-space:pre}
.copy-code{position:absolute;top:9px;right:10px;border:1px solid #b9c4cc;border-radius:4px;background:#fff;color:#33404a;padding:4px 10px;font:600 12px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;cursor:pointer}
.copy-code:hover{border-color:var(--accent);color:var(--accent-dark)}
.copy-code:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
table{width:100%;border-collapse:collapse;margin:18px 0 24px;background:var(--paper);font-size:15px}
td,th{border:1px solid var(--border);padding:9px 11px;vertical-align:top}
figure{margin:24px 0 30px;text-align:center;overflow-x:auto}
figure img{display:block;width:auto;height:auto;max-width:100%;max-height:76vh;object-fit:contain;margin:0 auto;background:var(--paper);border:1px solid var(--border);border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.demo-figure{max-width:720px;margin:22px auto 28px}
.demo-figure img{max-width:100%;max-height:62vh}
.demo-figure figcaption{max-width:680px;margin:10px auto 0;color:var(--muted);font-size:14px;line-height:1.55;text-align:left}
.demo-figure figcaption strong{display:block;color:#2b333c;font-size:15px;margin-bottom:3px}
.demo-figure figcaption span{display:block}
.demo-video{max-width:720px;margin:22px auto 28px}
.demo-video video{display:block;width:100%;max-height:62vh;background:#111;border:1px solid var(--border);border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.demo-video figcaption{max-width:680px;margin:10px auto 0;color:var(--muted);font-size:14px;line-height:1.55;text-align:left}
.demo-video figcaption strong{display:block;color:#2b333c;font-size:15px;margin-bottom:3px}
.demo-video figcaption span{display:block}
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
const isZh=document.documentElement.lang.toLowerCase().startsWith('zh');document.querySelectorAll('pre code').forEach(code=>{const pre=code.parentElement;if(!pre||pre.querySelector('.copy-code'))return;pre.classList.add('has-copy-button');const button=document.createElement('button');button.type='button';button.className='copy-code';button.textContent=isZh?'复制':'Copy';button.setAttribute('aria-label',isZh?'复制代码':'Copy code');button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(code.textContent);button.textContent=isZh?'已复制':'Copied'}catch(error){const range=document.createRange();range.selectNodeContents(code);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);button.textContent=isZh?'请按 Ctrl+C':'Press Ctrl+C'}setTimeout(()=>{button.textContent=isZh?'复制':'Copy'},1600)});pre.appendChild(button)})
""".strip() + "\n"


def write_root_files(manifest: dict[str, dict[str, int]]) -> None:
    (ROOT / "index.html").write_text('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=en/index.html"><title>Palm-sized UAV Experiment Manual</title></head><body><p><a href="en/index.html">English</a> &middot; <a href="zh/index.html">Chinese</a></p></body></html>\n', encoding="utf-8")
    (ROOT / ".nojekyll").write_text("", encoding="utf-8")
    (ROOT / "docs-manifest.json").write_text(json.dumps({"source_dir": str(SOURCE_DIR), "manuals": [manual.__dict__ for manual in MANUALS], "stats": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "README.md").write_text("""# Palm-sized UAV Experiment Manual

Bilingual experiment manual for palm-sized UAV summer school labs.

- The GitHub Pages root entry opens the English documentation by default.
- `zh/` contains Chinese experiment pages, including text, tables, links, commands, and figures.
- `en/` contains English experiment pages with language switches back to the Chinese pages.
- `.github/workflows/pages.yml` deploys the static site with GitHub Pages Actions.

## Course Materials

Download the `course-materials` folder from the [BUAA cloud link](https://bhpan.buaa.edu.cn/link/AA5DF49653676B4EDFBAB8B2A09B0FBEE9). The link is valid until 2028-11-11 10:31.

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
    image_count = sum(item["images"] for item in manifest.values())
    video_count = sum(item.get("videos", 0) for item in manifest.values())
    print(f"Built {len(MANUALS)} objective manuals with {image_count} images and {video_count} videos.")


if __name__ == "__main__":
    main()
