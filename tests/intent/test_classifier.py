"""M5 tests — ProblemClassifier heuristics."""

from friday.intent.classifier import ProblemClass, ProblemClassifier


def test_information_gathering():
    c = ProblemClassifier().classify("research the best laptops under 1000")
    assert c.primary is ProblemClass.INFORMATION_GATHERING


def test_creation():
    c = ProblemClassifier().classify("write a summary document about q3 sales")
    assert ProblemClass.CREATION in c.classes


def test_communication():
    c = ProblemClassifier().classify("email the report to my manager")
    assert c.primary is ProblemClass.COMMUNICATION


def test_navigation():
    c = ProblemClassifier().classify("open the settings page")
    assert c.primary is ProblemClass.NAVIGATION


def test_monitoring():
    c = ProblemClassifier().classify("alert me whenever the price drops")
    assert c.primary is ProblemClass.MONITORING


def test_automation():
    c = ProblemClassifier().classify("schedule a recurring daily backup")
    assert c.primary is ProblemClass.AUTOMATION


def test_multi_class_weights_sum_to_one():
    c = ProblemClassifier().classify("find the file and email it to me")
    assert len(c.classes) >= 2
    assert abs(sum(w for _, w in c.weights) - 1.0) < 0.01


def test_unknown_when_no_signal():
    c = ProblemClassifier().classify("zzz qqq")
    assert c.primary is ProblemClass.UNKNOWN


def test_reclassify_bumps_revision():
    classifier = ProblemClassifier()
    first = classifier.classify("do the thing")
    second = classifier.reclassify(first, "email the thing to bob")
    assert second.revision == 1
    assert second.primary is ProblemClass.COMMUNICATION


def test_no_app_specific_signals():
    """Anti-pattern check: classifier signals contain no app or site names."""
    from friday.intent.classifier import _SIGNALS

    banned = ("gmail", "instagram", "chrome", "vscode", "youtube", "facebook", "whatsapp")
    for signals in _SIGNALS.values():
        for signal in signals:
            assert not any(b in signal for b in banned), signal
