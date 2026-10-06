"""The reference extractor, on synthetic pages shaped like the real ones (no Abaqus text)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("extract_keyword_reference", ROOT / "scripts" / "extract_keyword_reference.py")
ekr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ekr)


def page(title: str, intro: str, type_: str, level: str) -> str:
    return (
        f"<html><head><title>{title}</title></head><body>"
        f"<h1>{title}</h1><p>{intro}</p><p>Products:</p><p>Abaqus/Standard</p>"
        f"<p>Type:</p><p>{type_}</p><p>Level:</p><p>{level}</p><p>Reference:</p></body></html>"
    )


def test_levels_and_types_are_parsed_including_part_instance():
    assert ekr._levels("Part,  Part instance,  Assembly") == ("part", "part instance", "assembly")
    assert ekr._levels("Part instance") == ("part instance",)       # must not also count as "part"
    assert ekr._levels("Model in Abaqus/Standard; Model or Step in Abaqus/Explicit") == ("model", "step")
    assert ekr._types("Model or history data") == ("model", "history")
    assert ekr._types("History data") == ("history",)


def test_parent_sentences_become_parents_and_typos_are_dropped(tmp_path):
    (tmp_path / "ch01abk01.html").write_text(page("*MATERIAL", "Begin a material definition.", "Model data", "Model"))
    (tmp_path / "ch01abk02.html").write_text(page(
        "*WIDGET", "It must be used in conjunction with the *MATERIAL option. Also see *NOSUCHTHING option.",
        "Model data", "Model"))
    (tmp_path / "ch01abk03.html").write_text(page(
        "*GADGET", "This option can be used only in conjunction with the *WIDGET and *MATERIAL options.",
        "History data", "Step"))
    facts = ekr.extract(tmp_path)
    assert facts["WIDGET"] == (("model",), ("model",), ("MATERIAL",))
    assert facts["GADGET"][2] == ("MATERIAL", "WIDGET")
    assert facts["MATERIAL"][2] == ()


def test_pages_that_are_not_keywords_are_skipped(tmp_path):
    (tmp_path / "ch01abk01.html").write_text(page("Introduction", "Not a keyword", "", ""))
    assert ekr.extract(tmp_path) == {}


def test_generated_module_round_trips(tmp_path):
    facts = {"ELASTIC": (("model",), ("model",), ()), "ELGEN": (("model",), ("part",), ("X",))}
    out = tmp_path / "keyword_reference.py"
    ekr.write(facts, out)
    ns: dict = {}
    exec(compile(out.read_text(), str(out), "exec"), ns)
    assert ns["FACTS"] == facts
