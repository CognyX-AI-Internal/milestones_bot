# -*- coding: utf-8 -*-
"""Deterministic screening arithmetic for the CMSP: B-5 bot.

Every number and age band in the report is computed here. The language model
receives the output of this module as authoritative facts and only writes prose.
It must never derive a band, a delay percentage, or an unmet-milestone list.

Key design decision: which bands count as "presumed met" is taken from the set of
bands actually administered (the keys present in the user's checklist state, which
the bot creates only when a band is rendered), never inferred from where ticks
happen to appear. A band that was shown and left empty is a failed band; a band
that was never shown is an unasked band. Those two cases are indistinguishable
from the ticks alone, and conflating them reports a child who ticked nothing as
mildly delayed.
"""

from collections import OrderedDict, namedtuple

Band = namedtuple("Band", ["key", "lo", "hi", "label"])

# Inclusive month bounds. `key` matches the keys of checklist_options.json.
BANDS = [
    Band(3, 0, 3, "Birth to 3 months"),
    Band(6, 4, 6, "4 to 6 months"),
    Band(9, 7, 9, "7 to 9 months"),
    Band(12, 10, 12, "10 to 12 months"),
    Band(18, 13, 18, "13 to 18 months"),
    Band(24, 19, 24, "19 to 24 months"),
    Band(36, 25, 36, "2 to 3 years"),
    Band(48, 37, 48, "3 to 4 years"),
    Band(60, 49, 60, "4 to 5 years"),
]

BAND_BY_KEY = {b.key: b for b in BANDS}
MAX_AGE_MONTHS = BANDS[-1].hi

# Delay states
DELAY_NONE = "none"          # no delay to report
DELAY_RANGE = "range"        # "X% to Y%"
DELAY_AT_LEAST = "at_least"  # "at least X%" - upper bound is meaningless


class OutOfScope(Exception):
    """Child's age falls outside the birth-to-5 range this instrument covers."""


def band_for_age(age_months):
    """Chronological band by inclusive bounds. Raises OutOfScope above 5 years.

    The instrument is birth-to-5; clamping a 70-month-old into the 4-to-5 band
    would silently report an out-of-scope screening as a valid one.
    """
    if age_months is None or age_months < 0:
        raise OutOfScope("Age is missing or negative: %r" % (age_months,))
    if age_months > MAX_AGE_MONTHS:
        raise OutOfScope(
            "Age %s months is above the birth-to-5 range of this screening tool."
            % age_months
        )
    for band in BANDS:
        if band.lo <= age_months <= band.hi:
            return band
    raise OutOfScope("No band covers age %s months." % age_months)


def _fmt(pct):
    return "%.2f%%" % pct


class ScreeningResult(object):
    """Everything the report needs, all of it computed, none of it inferred."""

    def __init__(self, age_months, chrono_band, dev_band, administered_keys,
                 presumed_keys, met, unmet, delay_state, delay_lo, delay_hi,
                 disclosure_needed, inconsistent):
        self.age_months = age_months
        self.chrono_band = chrono_band
        self.dev_band = dev_band
        self.administered_keys = administered_keys
        self.presumed_keys = presumed_keys
        self.met = met                # [(band_key, idx, text, domain)]
        self.unmet = unmet            # chronological band only
        self.delay_state = delay_state
        self.delay_lo = delay_lo
        self.delay_hi = delay_hi
        self.disclosure_needed = disclosure_needed
        self.inconsistent = inconsistent

    @property
    def all_met_for_age(self):
        return len(self.unmet) == 0

    @property
    def delay_text(self):
        if self.delay_state == DELAY_RANGE:
            return "%s to %s" % (_fmt(self.delay_lo), _fmt(self.delay_hi))
        if self.delay_state == DELAY_AT_LEAST:
            return "at least %s" % _fmt(self.delay_lo)
        return None

    @property
    def dev_band_label(self):
        # Phrased to read correctly inside "at the [X] developmental level".
        return self.dev_band.label if self.dev_band else "Below Birth to 3 months"


def analyze(age_months, checklists, checklist_options, milestone_domains):
    """Compute the full screening result.

    checklists: {band_key: [bool, ...]} - a key exists only for a band that was
        actually shown to the clinician. That is the administered set.
    """
    chrono = band_for_age(age_months)

    administered = sorted(int(k) for k in checklists.keys() if int(k) in BAND_BY_KEY)
    administered_set = set(administered)

    def ticks(band_key):
        raw = checklists.get(band_key, checklists.get(str(band_key), []))
        options = checklist_options.get(band_key, [])
        # Tolerate a stored list shorter/longer than the option list.
        return [bool(raw[i]) if i < len(raw) else False for i in range(len(options))]

    def counts_complete(band_key):
        """A band counts as complete if it was administered and fully ticked, or
        if it sits below the chronological band and was never administered."""
        if band_key in administered_set:
            flags = ticks(band_key)
            return len(flags) > 0 and all(flags)
        return band_key < chrono.key

    # Highest band that is complete with every band below it also complete.
    dev_band = None
    for band in BANDS:
        if all(counts_complete(b.key) for b in BANDS if b.key <= band.key):
            dev_band = band
        else:
            break

    presumed = [b.key for b in BANDS
                if b.key < chrono.key and b.key not in administered_set]

    def entries(band_key, want_met):
        flags = ticks(band_key)
        out = []
        for idx, text in enumerate(checklist_options.get(band_key, [])):
            is_met = flags[idx] if idx < len(flags) else False
            if is_met == want_met:
                domain = milestone_domains.get((band_key, idx), "Social Communication")
                out.append((band_key, idx, text, domain))
        return out

    met = []
    for band_key in administered:
        met.extend(entries(band_key, True))

    # Unmet is the chronological band only - never any other band.
    unmet = entries(chrono.key, False) if chrono.key in administered_set else []
    all_met = len(unmet) == 0

    delay_state, delay_lo, delay_hi = _compute_delay(age_months, dev_band, all_met)

    # Disclose only when the developmental band itself was presumed rather than
    # demonstrated. Presuming bands below a demonstrated floor is standard basal
    # practice and needs no caveat; presuming the floor itself does.
    disclosure_needed = bool(
        dev_band is not None
        and dev_band.key not in administered_set
        and delay_state != DELAY_NONE
    )

    # Chronological band complete while an administered lower band is not: the
    # walk-down contradicts the current band. Surface it rather than average it.
    inconsistent = bool(
        all_met and dev_band is not None and dev_band.key < chrono.key
    )

    return ScreeningResult(
        age_months=age_months, chrono_band=chrono, dev_band=dev_band,
        administered_keys=administered, presumed_keys=presumed,
        met=met, unmet=unmet, delay_state=delay_state, delay_lo=delay_lo,
        delay_hi=delay_hi, disclosure_needed=disclosure_needed,
        inconsistent=inconsistent,
    )


def _compute_delay(age_months, dev_band, all_met):
    """Delay depends only on the developmental band boundary and the age, never
    on how many milestones were missed. 1-of-6 and 4-of-6 give the same range."""
    if all_met:
        return DELAY_NONE, None, None

    if dev_band is None:
        # Not even the earliest band is complete: developmental age is below it.
        lo = ((age_months - BANDS[0].hi) / float(age_months)) * 100 if age_months else 0
        return (DELAY_AT_LEAST, lo, None) if lo > 0 else (DELAY_NONE, None, None)

    lo = ((age_months - dev_band.hi) / float(age_months)) * 100

    if dev_band.lo == 0:
        # The band starts at month 0, so the upper bound is always exactly 100%
        # - an artifact of the boundary, not a finding. Report a minimum only.
        return (DELAY_AT_LEAST, lo, None) if lo > 0 else (DELAY_NONE, None, None)

    hi = ((age_months - dev_band.lo) / float(age_months)) * 100
    if hi > 0 and lo >= 0:
        return DELAY_RANGE, lo, hi
    return DELAY_NONE, None, None


# --------------------------------------------------------------------------
# FACTS block
# --------------------------------------------------------------------------

DOMAIN_ORDER = ["Expressive Language", "Receptive Language", "Social Communication"]


def _group_by_band_and_domain(entries):
    grouped = OrderedDict()
    for band_key, idx, text, domain in entries:
        grouped.setdefault(band_key, OrderedDict())
        grouped[band_key].setdefault(domain, []).append(text)
    return grouped


def _render_milestones(entries, indent="  "):
    lines = []
    for band_key, by_domain in _group_by_band_and_domain(entries).items():
        lines.append("%s[%s]" % (indent, BAND_BY_KEY[band_key].label))
        for domain in DOMAIN_ORDER:
            if domain not in by_domain:
                continue
            lines.append("%s  %s:" % (indent, domain))
            for text in by_domain[domain]:
                lines.append("%s    - %s" % (indent, text))
    return "\n".join(lines)


def build_facts_block(result):
    """The VERIFIED FACTS block appended to the model's user message."""
    lines = [
        "",
        "===== VERIFIED FACTS (computed by the screening software - authoritative) =====",
        "CHRONOLOGICAL_AGE: %s months" % result.age_months,
        "CURRENT_CHRONOLOGICAL_AGE_RANGE: %s" % result.chrono_band.label,
        "DEVELOPMENTAL_AGE_RANGE: %s" % result.dev_band_label,
        "ALL_MILESTONES_MET_FOR_CURRENT_RANGE: %s" % ("YES" if result.all_met_for_age else "NO"),
    ]

    if result.disclosure_needed and result.presumed_keys:
        labels = [BAND_BY_KEY[k].label for k in result.presumed_keys]
        lines.append(
            "SCREENING_SCOPE: the following earlier age bands were NOT administered and are "
            "PRESUMED MET: %s. The developmental age range and delay percentage above are "
            "calculated on that basis. You MUST state this limitation once, plainly, in the "
            "Observations section - for example: \"Milestones for the %s through %s ranges were "
            "not administered during this screening and are presumed to have been met; the "
            "developmental age range and percentage of delay are calculated on that basis.\" "
            "Do not present the delay as a fully screened result."
            % (", ".join(labels), labels[0], labels[-1])
        )

    if result.delay_state == DELAY_NONE:
        lines.append(
            "DELAY_PERCENTAGE: NONE - there is NO delay. Do not state, imply, or print any percentage."
        )
    elif result.delay_state == DELAY_AT_LEAST:
        lines.append(
            "DELAY_PERCENTAGE: %s (pre-computed, use verbatim, do not recalculate). State this as a "
            "minimum, not a range. Do not print an upper bound and never print 100%%. Write it as "
            "\"a delay of at least %s\" - drop the word \"approximately\" from the template sentence, "
            "because \"approximately at least\" does not read as clinical English."
            % (result.delay_text, _fmt(result.delay_lo))
        )
    else:
        lines.append(
            "DELAY_PERCENTAGE: %s (pre-computed, use verbatim, do not recalculate)"
            % result.delay_text
        )

    if result.inconsistent:
        lines.append(
            "DATA_INCONSISTENCY: the child met every milestone for their current age range, but an "
            "earlier age range that WAS administered is incomplete. Report no delay, and note in "
            "Recommendations for the Clinical Team that the earlier-range responses should be "
            "reviewed for accuracy."
        )

    lines.append("")
    lines.append("MILESTONES_MET (verbatim from the screening tool, pre-grouped by domain):")
    lines.append(_render_milestones(result.met) if result.met else "  NONE")
    lines.append("")

    if result.all_met_for_age:
        lines.append(
            "MILESTONES_NOT_MET: NONE. Omit the \"Milestones Expected but Not Met\" section "
            "entirely. Because nothing is unmet, base BOTH Recommendations sections on ENRICHMENT "
            "and continued growth rather than remediation, and still produce both sections in "
            "full. Do not invent a delay percentage or claim a delay the checklist does not show."
        )
    else:
        lines.append(
            "MILESTONES_NOT_MET (exactly these %d, and ONLY these - all from %s. Do not add "
            "milestones from any other band):" % (len(result.unmet), result.chrono_band.label)
        )
        lines.append(_render_milestones(result.unmet))

    lines.append("")
    lines.append(
        "SAFETY OVERRIDE: these conclusions reflect the CHECKLIST ONLY. If the parent or clinician "
        "narrative describes anything that contradicts them - not speaking, not responding to their "
        "name, loss of previously held skills, no eye contact, or a hearing concern - you MUST "
        "surface that contradiction in the Observations section and recommend appropriate follow-up "
        "(such as audiological or developmental evaluation) under Recommendations for the Clinical "
        "Team. A checklist result must never suppress a reported red flag."
    )
    lines.append("===== END VERIFIED FACTS =====")
    return "\n".join(lines)
