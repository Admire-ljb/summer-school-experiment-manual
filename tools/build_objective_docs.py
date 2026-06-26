from __future__ import annotations

import html
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT.parent / "\u5b9e\u9a8c\u624b\u518c"
ASSET_DIR = ROOT / "assets"
IMAGE_DIR = ASSET_DIR / "images"

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
    for path in [ROOT / "zh", ROOT / "en", IMAGE_DIR]:
        if path.exists():
            shutil.rmtree(path)
    (ROOT / "zh").mkdir(parents=True, exist_ok=True)
    (ROOT / "en").mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)


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
    out_path.write_bytes(zf.read(source_name))
    return f"../assets/images/{manual.slug}/{out_path.name}"


def para_to_html(text: str, style: str, images: list[str]) -> str:
    stripped = text.strip()
    blocks: list[str] = []
    if stripped:
        escaped = html.escape(stripped)
        if stripped in {"\u4e00\u3001\u5b9e\u9a8c\u76ee\u6807", "\u4e8c\u3001\u5b9e\u9a8c\u51c6\u5907", "\u4e09\u3001\u5b9e\u9a8c\u6b65\u9aa4", "\u56db\u3001\u5b9e\u9a8c\u9a8c\u8bc1\u4e0e\u6d4b\u8bd5", "\u4e94\u3001\u5b9e\u9a8c\u603b\u7ed3\u4e0e\u62d3\u5c55", "\u94fe\u63a5\u8d44\u6599\u6574\u7406"}:
            blocks.append(f"<h2>{escaped}</h2>")
        elif re.match(r"^\u9636\u6bb5\s*\d+", stripped) or style.lower().startswith("heading"):
            blocks.append(f"<h3>{escaped}</h3>")
        elif stripped.startswith(("http://", "https://")) or re.match(r"^(sudo|pip|python|ros|catkin|source|git|cd|mkdir|ping|reboot)\b", stripped):
            blocks.append(f"<pre><code>{escaped}</code></pre>")
        elif re.match(r"^[0-9]+[.)]\s", stripped):
            blocks.append(f'<p class="step">{escaped}</p>')
        else:
            blocks.append(f"<p>{escaped}</p>")
    for src in images:
        blocks.append(f'<figure><img src="{html.escape(src)}" alt="{html.escape(stripped[:80] or "manual image")}" loading="lazy"></figure>')
    return "\n".join(blocks)


def table_to_html(table: ET.Element) -> str:
    rows = []
    for tr in table.findall("./w:tr", NS):
        cells = [f"<td>{html.escape(text_from(tc))}</td>" for tc in tr.findall("./w:tc", NS)]
        if cells:
            rows.append("<tr>" + "".join(cells) + "</tr>")
    return "" if not rows else "<table><tbody>\n" + "\n".join(rows) + "\n</tbody></table>"


def extract_manual(manual: Manual) -> tuple[list[str], dict[str, int]]:
    source = SOURCE_DIR / manual.source_name
    if not source.exists():
        raise FileNotFoundError(source)
    blocks: list[str] = []
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
                    blocks.append(para_to_html(text, paragraph_style(child), images))
            elif child.tag == f"{{{NS['w']}}}tbl":
                table = table_to_html(child)
                if table:
                    stats["tables"] += 1
                    blocks.append(table)
    return blocks, stats


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
    other = "en" if lang == "zh" else "zh"
    other_label = "English" if lang == "zh" else "\u4e2d\u6587"
    current_label = "\u4e2d\u6587" if lang == "zh" else "English"
    other_href = f"../{other}/index.html" if current_slug is None else f"../{other}/{current_slug}.html"
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
        <div class="language-switch"><span>{current_label}</span><a href="{other_href}">{other_label}</a></div>
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
            "<p>\u672c\u6587\u6863\u4f7f\u7528 <code>D:/\u6691\u671f\u5b66\u6821/\u5b9e\u9a8c\u624b\u518c</code> "
            "\u4e2d\u7684\u5b9e\u9a8c\u624b\u518c\u7d20\u6750\u751f\u6210\uff0c\u6309\u5b9e\u9a8c\u7f16\u53f7\u7ec4\u7ec7\uff0c\u4e0d\u6309\u65e5\u671f\u5206\u7ec4\u3002"
            "\u9875\u9762\u91c7\u7528\u7c7b\u4f3c ReadTheDocs \u7684\u5de6\u4fa7\u5bfc\u822a\u3001\u6b63\u6587\u9605\u8bfb\u533a\u548c\u4e2d\u82f1\u6587\u5207\u6362\u7ed3\u6784\u3002</p>"
            "<div class=\"admonition warning\"><p class=\"admonition-title\">\u5b89\u5168\u8bf4\u660e</p>"
            "<p>\u6d89\u53ca\u771f\u5b9e\u98de\u884c\u7684\u5b9e\u9a8c\u5fc5\u987b\u5728\u6559\u5e08\u6216\u52a9\u6559\u786e\u8ba4\u573a\u5730\u3001\u8bbe\u5907\u3001\u7535\u6c60\u548c\u6025\u505c\u6d41\u7a0b\u540e\u8fdb\u884c\u3002</p></div>"
            "<h2>\u5b9e\u9a8c\u76ee\u5f55</h2><div class=\"toctree-wrapper\">"
        )
        for manual in MANUALS:
            body += f'<a class="doc-card" href="{manual.slug}.html"><span>\u5b9e\u9a8c {manual.number}</span><strong>{html.escape(manual.zh_title)}</strong><em>{html.escape(manual.en_title)}</em></a>\n'
        body += "</div>"
        title = "\u638c\u4e0a\u65e0\u4eba\u673a\u5b9e\u9a8c\u624b\u518c"
    else:
        body = "<h1>Palm-sized UAV Experiment Manual</h1><p>This documentation site is generated only from the source material in <code>D:/\u6691\u671f\u5b66\u6821/\u5b9e\u9a8c\u624b\u518c</code>. It is organized by experiment number rather than by date. The layout follows a ReadTheDocs-style documentation format with navigation, content pages, and bilingual switching.</p><div class=\"admonition warning\"><p class=\"admonition-title\">Safety note</p><p>Experiments involving real flight must be conducted only after the instructor or teaching assistant confirms the arena, equipment, batteries, and emergency-stop procedure.</p></div><h2>Experiment list</h2><div class=\"toctree-wrapper\">"
        for manual in MANUALS:
            body += f'<a class="doc-card" href="{manual.slug}.html"><span>Experiment {manual.number}</span><strong>{html.escape(manual.en_title)}</strong><em>{html.escape(manual.zh_title)}</em></a>\n'
        body += "</div>"
        title = "Palm-sized UAV Experiment Manual"
    (ROOT / lang / "index.html").write_text(layout(lang, title, body), encoding="utf-8")

def english_body(manual: Manual, stats: dict[str, int]) -> str:
    prep = "".join(f"<li>{html.escape(item)}</li>" for item in manual.preparation)
    proc = "".join(f"<li>{html.escape(item)}</li>" for item in manual.procedure)
    verify = "".join(f"<li>{html.escape(item)}</li>" for item in manual.verification)
    return f"""
<h1>Experiment {manual.number}: {html.escape(manual.en_title)}</h1>
<p class="subtitle">{html.escape(manual.zh_title)}</p>
<div class="admonition note"><p class="admonition-title">Source-based English document</p><p>This page is an objective English document derived from the corresponding Word manual in the local source folder. The Chinese page keeps the extracted original text, tables, links, commands, and figures.</p></div>
<h2>Purpose</h2>
<p>{html.escape(manual.purpose)}</p>
<h2>Preparation</h2>
<ul>{prep}</ul>
<h2>Procedure</h2>
<ol>{proc}</ol>
<h2>Verification</h2>
<ul>{verify}</ul>
<h2>Source Material</h2>
<p>The extracted Chinese companion page contains {stats['paragraphs']} text/image blocks, {stats['tables']} tables, and {stats['images']} images. Source file names are retained in <code>docs-manifest.json</code> for reproducibility.</p>
"""


def write_pages() -> dict[str, dict[str, int]]:
    manifest: dict[str, dict[str, int]] = {}
    for manual in MANUALS:
        blocks, stats = extract_manual(manual)
        manifest[manual.slug] = stats
        zh_body = f'<h1>\u5b9e\u9a8c {manual.number}: {html.escape(manual.zh_title)}</h1><p class="subtitle">{html.escape(manual.en_title)}</p>' + "\n".join(blocks)
        (ROOT / "zh" / f"{manual.slug}.html").write_text(layout("zh", manual.zh_title, zh_body, manual.slug), encoding="utf-8")
        (ROOT / "en" / f"{manual.slug}.html").write_text(layout("en", manual.en_title, english_body(manual, stats), manual.slug), encoding="utf-8")
    return manifest


def write_assets() -> None:
    (ASSET_DIR / "style.css").write_text(STYLE, encoding="utf-8")
    (ASSET_DIR / "site.js").write_text(SCRIPT, encoding="utf-8")


STYLE = """
:root{--sidebar:#343131;--sidebar-dark:#2a2727;--sidebar-link:#d9d9d9;--accent:#2980b9;--accent-dark:#1f5f8b;--text:#404040;--muted:#777;--border:#e1e4e5;--code:#f3f6f6}*{box-sizing:border-box}body{margin:0;color:var(--text);background:#edf0f2;font-family:"Lato","Segoe UI","Noto Sans SC","Microsoft YaHei",Arial,sans-serif;line-height:1.65}a{color:var(--accent);text-decoration:none}a:hover{color:var(--accent-dark);text-decoration:underline}.wy-nav-side{position:fixed;inset:0 auto 0 0;width:300px;overflow:hidden;background:var(--sidebar);color:var(--sidebar-link)}.wy-side-scroll{height:100%;overflow-y:auto}.wy-side-nav-search{background:var(--accent);color:#fff;padding:24px 18px 18px;text-align:center}.icon-home{display:block;color:#fff;font-size:20px;font-weight:700;line-height:1.25}.icon-home:hover{color:#fff}.version{margin:8px 0 16px;font-size:13px;opacity:.85}#doc-search{width:100%;height:36px;border:0;border-radius:4px;padding:0 10px;color:#333}.wy-menu{padding:16px 0 32px}.caption{margin:0;padding:0 20px 8px;color:#55a5d9;font-size:12px;font-weight:700;text-transform:uppercase}.wy-menu ul{list-style:none;padding:0;margin:0}.wy-menu a{display:block;color:var(--sidebar-link);padding:10px 20px;border-left:4px solid transparent}.wy-menu a span{display:block;color:#9db9c9;font-size:12px;margin-bottom:2px}.wy-menu a.active,.wy-menu a:hover{background:var(--sidebar-dark);border-left-color:var(--accent);color:#fff;text-decoration:none}.wy-nav-content-wrap{margin-left:300px;min-height:100vh}.wy-nav-content{background:#fcfcfc;min-height:100vh;padding:34px 48px 80px}.rst-content{max-width:920px;margin:0 auto}.breadcrumbs{position:relative;color:var(--muted);font-size:14px;border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:18px}.breadcrumbs span{margin:0 6px}.github-link{float:right}.language-switch{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin:0 0 10px;font-size:14px}.language-switch span,.language-switch a{border:1px solid var(--border);border-radius:4px;padding:4px 9px}.language-switch span{background:#f3f6f6;color:#555}h1,h2,h3{color:#222;font-family:"Roboto Slab","Noto Serif SC",Georgia,serif;font-weight:700;line-height:1.3}h1{font-size:34px;margin:20px 0 16px}h2{font-size:24px;margin-top:34px;border-bottom:1px solid var(--border);padding-bottom:6px}h3{font-size:19px;margin-top:26px}.subtitle{color:var(--muted);font-size:16px;margin-top:-8px}p{margin:0 0 14px}ul,ol{padding-left:24px}li{margin:6px 0}code{background:var(--code);border:1px solid #d6d8d8;border-radius:4px;padding:1px 5px;font-family:Consolas,"SFMono-Regular",monospace}pre{background:var(--code);border:1px solid #d6d8d8;border-radius:4px;overflow-x:auto;padding:12px 14px}pre code{border:0;padding:0}table{width:100%;border-collapse:collapse;margin:16px 0;background:#fff}td,th{border:1px solid var(--border);padding:8px 10px;vertical-align:top}figure{margin:18px 0}figure img{max-width:100%;border:1px solid var(--border);border-radius:4px;box-shadow:0 1px 2px rgba(0,0,0,.08)}.admonition{border-left:4px solid var(--accent);background:#eef7fc;padding:12px 16px;margin:18px 0}.admonition.warning{border-left-color:#c45f18;background:#fff5eb}.admonition-title{font-weight:700;margin-bottom:6px}.toctree-wrapper{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-top:16px}.doc-card{display:block;background:#fff;border:1px solid var(--border);border-radius:6px;padding:14px 16px}.doc-card:hover{text-decoration:none;border-color:var(--accent)}.doc-card span{display:inline-block;color:#fff;background:var(--accent);border-radius:3px;padding:1px 6px;font-size:12px;margin-bottom:8px}.doc-card strong{display:block;color:#222}.doc-card em{display:block;color:var(--muted);font-style:normal;font-size:14px}.step{padding-left:12px;border-left:3px solid #d9e8f2}.mobile-bar{display:none;align-items:center;gap:12px;background:var(--sidebar);color:#fff;padding:10px 14px}#menu-toggle{appearance:none;border:1px solid rgba(255,255,255,.35);background:transparent;color:#fff;border-radius:4px;width:34px;height:32px;font-size:20px}.hidden-by-search{display:none!important}@media(max-width:900px){.wy-nav-side{transform:translateX(-100%);transition:transform .2s ease;z-index:10}body.nav-open .wy-nav-side{transform:translateX(0)}.wy-nav-content-wrap{margin-left:0}.mobile-bar{display:flex;position:sticky;top:0;z-index:5}.wy-nav-content{padding:22px 20px 64px}h1{font-size:28px}.github-link{float:none;display:block;margin-top:8px}}
""".strip() + "\n"

SCRIPT = """
const toggle=document.getElementById('menu-toggle');if(toggle){toggle.addEventListener('click',()=>document.body.classList.toggle('nav-open'))}const search=document.getElementById('doc-search');const navItems=Array.from(document.querySelectorAll('#nav-list li'));if(search){search.addEventListener('input',()=>{const q=search.value.trim().toLowerCase();navItems.forEach(item=>{const text=item.textContent.toLowerCase();item.classList.toggle('hidden-by-search',q&&!text.includes(q))})})}
""".strip() + "\n"


def write_root_files(manifest: dict[str, dict[str, int]]) -> None:
    (ROOT / "index.html").write_text('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=zh/index.html"><title>Palm-sized UAV Experiment Manual</title></head><body><p><a href="zh/index.html">\u4e2d\u6587</a> &middot; <a href="en/index.html">English</a></p></body></html>\n', encoding="utf-8")
    (ROOT / ".nojekyll").write_text("", encoding="utf-8")
    (ROOT / "docs-manifest.json").write_text(json.dumps({"source_dir": str(SOURCE_DIR), "manuals": [manual.__dict__ for manual in MANUALS], "stats": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "README.md").write_text("""# Palm-sized UAV Experiment Manual

ReadTheDocs-style bilingual documentation generated from `D:/\u6691\u671f\u5b66\u6821/\u5b9e\u9a8c\u624b\u518c`.

- Organized by experiment number rather than by date.
- `zh/` contains the extracted Chinese source pages, including text, tables, links, commands, and figures.
- `en/` contains objective English experiment-document pages with language switches back to the Chinese source pages.
- `.github/workflows/pages.yml` deploys the static site with GitHub Pages Actions.

## Local preview

Open `index.html` in a browser, or serve this directory with any static file server.

## Regenerate

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

