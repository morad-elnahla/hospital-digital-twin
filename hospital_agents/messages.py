"""Structured, bilingual messages.

Every human-readable reason the agents, constraints and arbitration produce is a `Msg`: a `str`
whose value is the canonical English text (so logs, audit and existing consumers keep working)
that also carries a stable `code` and its `params`. A message can therefore be rendered in any
supported language *after the fact* without re-running the agents, and the UI can branch on the
code instead of searching text.

Rules that keep this honest:
  * A rendering only re-words what the params already say; it never adds a number.
  * Param values may be other `Msg` objects (or lists of them); they are rendered recursively.
  * An unknown code or language falls back to English, never to an empty string.
"""
from __future__ import annotations

import string
from typing import Any, Iterable

LANGS = ("en", "ar")


def _is_one(value: Any) -> bool:
    try:
        return float(value) == 1.0
    except (TypeError, ValueError):
        return False


def plural(n: Any, one: str, many: str | None = None) -> str:
    """English noun/verb agreement: `plural(1, "bed")` -> "bed", `plural(2, "bed")` -> "beds".

    Exactly 1 takes the singular; 0, 2, 1.5 ... take the plural. Irregular forms pass `many`
    explicitly (`plural(n, "surgery", "surgeries")`).
    """
    return one if _is_one(n) else (many if many is not None else one + "s")


def count(n: Any, one: str, many: str | None = None) -> str:
    """The number with its noun: `count(1, "bed")` -> "1 bed", `count(12, "bed")` -> "12 beds"."""
    shown = f"{n:g}" if isinstance(n, float) else str(n)
    return f"{shown} {plural(n, one, many)}"


class _Formatter(string.Formatter):
    """str.format plus an agreement spec: `{beds:bed/beds}` -> "bed" or "beds" depending on the value.

    Written next to the number (`{beds} {beds:bed/beds}`), so the template says what it means and a
    count can never be paired with the wrong form. Any other spec (`g`, `.1f`, `+d`, `,.0f`) is untouched.
    """

    def format_field(self, value: Any, format_spec: str) -> str:
        if "/" in format_spec:
            one, many = format_spec.split("/", 1)
            return one if _is_one(value) else many
        return super().format_field(value, format_spec)


_FORMATTER = _Formatter()


def format_text(template: str, **params: Any) -> str:
    """Render a template with agreement specs (used by every message and by the executive summary)."""
    return _FORMATTER.vformat(template, (), params)

AGENT_AR = {"er": "الطوارئ", "bed": "الأسرّة", "staff": "الطاقم", "or": "غرف العمليات",
            "appointment": "المواعيد", "resource": "الموارد", "finance": "المالية"}
UNIT_AR = {"ER": "الطوارئ", "ICU": "العناية المركزة", "WARD": "القسم الداخلي", "OR": "غرف العمليات",
           "CLINIC": "العيادات"}
KIND_AR = {"beds": "الأسرّة", "nurses": "التمريض", "doctors": "الأطباء"}

# code -> (English, Arabic). Placeholders use str.format syntax.
CATALOG: dict[str, tuple[str, str]] = {
    # ───────── titles / actions ─────────
    "title.rebalance": ("{agent}: rebalance {pool} by +{covered}", "{agent}: إعادة توزيع {pool} بمقدار +{covered}"),
    "title.move": ("{agent}: move booking {booking}", "{agent}: نقل الحجز {booking}"),
    "title.finance": ("finance: revenue-at-risk alert", "المالية: تنبيه إيراد معرّض للخطر"),
    "act.pool": ("{pool} {delta:+d}", "{pool} {delta:+d}"),
    "act.move": ("move {booking} from {src} to {dst}", "نقل {booking} من {src} إلى {dst}"),
    "act.alert": ("alert: {detail}", "تنبيه: {detail}"),
    "act.line": ("{agent}: {actions}", "{agent}: {actions}"),
    # ───────── capacity rebalancing ─────────
    "reb.no_forecast": ("{unit}:{kind}: no demand forecast passed rolling-origin validation; unit excluded as donor",
                        "{unit}:{kind}: لا يوجد توقع طلب اجتاز التحقق المتحرك؛ استُبعدت الوحدة كجهة مانحة"),
    "reb.no_headroom": ("{pool}: deficit {deficit} but no headroom or donor surplus",
                        "{pool}: يوجد عجز {deficit} لكن لا توجد سعة إضافية ولا فائض لدى وحدات مانحة"),
    "reb.need": ("{pool} forecast peak demand {demand:.1f} at target utilisation {target:g} requires {required}, current total {total}",
                 "ذروة الطلب المتوقع لـ {pool} هي {demand:.1f}؛ عند نسبة استخدام مستهدفة {target:g} يلزم {required} والإجمالي الحالي {total}"),
    "reb.cover": ("deficit {deficit}, covered {covered}, unmet {unmet}",
                  "العجز {deficit}، المغطى {covered}، غير المغطى {unmet}"),
    "reb.nurse_cap": ("nursing limit: {nurses} {nurses:nurse/nurses} on shift at {ratio:g} {ratio:patient/patients} per nurse can staff at most {max_beds} {max_beds:bed/beds} in {unit}; "
                      "the move was sized to +{covered} instead of +{wanted}",
                      "حد التمريض: {nurses} ممرض/ة في الوردية بنسبة {ratio:g} مريض لكل ممرض يدعمون {max_beds} سرير كحد أقصى في {unit}؛ "
                      "فتم تحجيم النقل إلى +{covered} بدلًا من +{wanted}"),
    "reb.nurse_blocked": ("nursing limit: {nurses} {nurses:nurse/nurses} on shift at {ratio:g} {ratio:patient/patients} per nurse can staff at most {max_beds} {max_beds:bed/beds} in {unit}, "
                          "which does not allow more than the current {total}; the full move is proposed so the gate can reject it with the numbers",
                          "حد التمريض: {nurses} ممرض/ة في الوردية بنسبة {ratio:g} مريض لكل ممرض يدعمون {max_beds} سرير كحد أقصى في {unit} "
                          "ولا يسمح ذلك بأكثر من {total} الحالية؛ يُقترح النقل كاملًا ليرفضه الفحص مع الأرقام"),
    "reb.abstain_resource": ("no resource-specific demand forecast passed rolling-origin validation; abstaining",
                             "لا يوجد توقع طلب خاص بالموارد اجتاز التحقق المتحرك؛ امتنع الوكيل"),
    # ───────── OR / appointment ─────────
    "or.pool_missing": ("{key}: pool or demand forecast that passed rolling-origin validation is missing; abstaining",
                        "{key}: المجمّع أو توقع الطلب الذي اجتاز التحقق المتحرك غير متوفر؛ امتنع الوكيل"),
    "or.deficit": ("{key} forecast peak demand {demand:.1f} exceeds capacity {total} (deficit {deficit})",
                   "ذروة الطلب المتوقع لـ {key} هي {demand:.1f} وتتجاوز السعة {total} (العجز {deficit})"),
    "or.candidate": ("booking {booking} is non_urgent and flagged needs_icu_bed",
                     "الحجز {booking} غير عاجل ومعلَّم بأنه يحتاج سرير عناية"),
    "or.assumed": ("assumed beds freed per procedure: {beds:g} (an assumption, not simulated)",
                   "افتراض عدد الأسرّة المتحررة لكل عملية: {beds:g} (افتراض وليس نتيجة محاكاة)"),
    "or.verified_slot": ("capacity slot {room} on {day} has {free} free {free:minute/minutes} of {capacity} inside the known calendar (ends {until}); provider/team compatibility is checked separately",
                         "سعة الموعد في {room} يوم {day} فيها {free} دقيقة متاحة من {capacity} ضمن الجدول المعروف (ينتهي {until})؛ ويُتحقق من توافق المختص أو الفريق بصورة منفصلة"),
    "or.no_slot": ("booking {booking}: no verified free slot in {room} after the forecast horizon; the schedule data ends {until}",
                   "الحجز {booking}: لا يوجد موعد متاح مؤكد في {room} بعد أفق التوقع؛ بيانات الجدول تنتهي {until}"),
    "or.no_slot_unknown": ("booking {booking}: no verified free slot in {room} after the forecast horizon",
                           "الحجز {booking}: لا يوجد موعد متاح مؤكد في {room} بعد أفق التوقع"),
    "appt.over": ("slot {resource}@{start} booked {booked} over capacity {capacity}",
                  "الموعد {resource}@{start} محجوز {booked} فوق السعة {capacity}"),
    "appt.partial": ("slot {resource}@{start}: overbooked by {excess} but only {freed} is movable (non_urgent)",
                     "الموعد {resource}@{start}: زيادة الحجز {excess} لكن المتاح للنقل {freed} فقط (غير عاجل)"),
    "appt.no_slot": ("booking {booking}: no later free slot in {resource}", "الحجز {booking}: لا يوجد موعد لاحق متاح في {resource}"),
    # ───────── finance ─────────
    "fin.abstain": ("revenue threshold or baseline missing; abstaining", "حد الإيراد أو خط الأساس غير متوفر؛ امتنع الوكيل"),
    "fin.alert": ("baseline revenue at risk {base:,.0f} EGP exceeds threshold {threshold:,.0f} EGP",
                  "الإيراد المعرّض للخطر في خط الأساس {base:,.0f} جنيه يتجاوز الحد {threshold:,.0f} جنيه"),
    "fin.rationale": ("simulation {run} baseline revenue_at_risk_egp={base:g}", "خط أساس المحاكاة {run}: الإيراد المعرّض للخطر = {base:g}"),
    "fin.threshold": ("threshold={threshold:g}", "الحد = {threshold:g}"),
    # ───────── constraints ─────────
    "pool.unknown": ("{pool}: unknown pool", "{pool}: مجمّع غير معروف"),
    "pool.below_committed": ("{pool}: total would drop to {new}, below committed {committed}",
                             "{pool}: الإجمالي سينخفض إلى {new} وهو أقل من المشغول {committed}"),
    "pool.over_max": ("{pool}: total {new} exceeds hard max {hard_max}", "{pool}: الإجمالي {new} يتجاوز الحد الأقصى الفعلي {hard_max}"),
    "pool.no_max": ("{pool}: net growth without a known hard max", "{pool}: زيادة صافية بدون حد أقصى فعلي معروف"),
    "slot.booking": ("booking {booking}: {why}", "الحجز {booking}: {why}"),
    "slot.unknown_booking": ("unknown booking", "حجز غير معروف"),
    "slot.not_movable": ("only non_urgent bookings may be moved", "يُسمح بنقل الحجوزات غير العاجلة فقط"),
    "slot.from_mismatch": ("from_slot does not match the twin", "الموعد الأصلي لا يطابق بيانات التوأم"),
    "slot.beyond_calendar": ("target slot {start} is outside the known calendar, which ends {until}; an empty future is unknown, not free",
                             "الموعد المستهدف {start} خارج الجدول المعروف الذي ينتهي {until}؛ المستقبل الفارغ مجهول وليس متاحًا"),
    "slot.missing": ("target slot does not exist", "الموعد المستهدف غير موجود"),
    "slot.domain_or_past": ("target slot is in another domain or in the past", "الموعد المستهدف في مجال آخر أو في الماضي"),
    "slot.provider": ("provider {provider} not verified available for target slot", "المختص {provider} غير مؤكد التوفر في الموعد المستهدف"),
    "slot.team_unverifiable": ("UNVERIFIABLE: no provider or case team is recorded for this surgery", "غير قابل للتحقق: لا يوجد مختص أو فريق مسجل لهذه العملية"),
    "slot.team": ("case team {team} is not verified available for target slot", "فريق العملية {team} غير مؤكد التوفر في الموعد المستهدف"),
    "slot.specialty_unverifiable": ("UNVERIFIABLE: case or operating-room specialty is missing", "غير قابل للتحقق: تخصص العملية أو غرفة العمليات غير متاح"),
    "slot.specialty": ("case specialty {specialty} is incompatible with target-room specialty {target}", "تخصص العملية {specialty} غير متوافق مع تخصص الغرفة المستهدفة {target}"),
    "slot.overclaimed": ("slot {resource}@{start}: {claimed} claimed for {free} free", "الموعد {resource}@{start}: المطلوب {claimed} والمتاح {free}"),
    "slot.moved_twice": ("booking {booking} moved by several proposals", "الحجز {booking} مطلوب نقله بأكثر من اقتراح"),
    "nurse.unverifiable": ("{unit}: nurse-ratio policy or pools unavailable; change is unverifiable",
                           "{unit}: سياسة نسبة التمريض أو المجمّعات غير متاحة؛ لا يمكن التحقق من التغيير"),
    "nurse.exceeds": ("{unit}: {beds} {beds:bed/beds} / {nurses} {nurses:nurse/nurses} exceeds {limit:g} {limit:patient/patients} per nurse (policy {source}); "
                      "{beds} {beds:bed/beds} {beds:needs/need} at least {required} {required:nurse/nurses}, {nurses} on shift (supports {supported} {supported:bed/beds})",
                      "{unit}: {beds} سرير لكل {nurses} ممرض يتجاوز {limit:g} مريض لكل ممرض (السياسة {source})؛ "
                      "يلزم {required} ممرض على الأقل لـ {beds} سرير والمتاح {nurses} في الوردية (يدعمون {supported} سرير)"),
    # ───────── arbitration ─────────
    "arb.no_actions": ("proposal has no actions", "الاقتراح لا يحتوي على إجراءات"),
    "arb.reason": ("{constraint}: {message}", "{constraint}: {message}"),
    "arb.joint": ("removed in joint check - {reasons}", "أُزيل في الفحص المشترك - {reasons}"),
    # ───────── executive card ─────────
    "as.forecast": ("forecast {model}, planned on its {stat} value", "التوقع {model}، والتخطيط على قيمته {stat}"),
    "forecast.point_no_interval": ("point (no calibrated interval)", "تقدير نقطي (من دون نطاق معاير)"),
    "as.twin": ("twin snapshot {version}", "لقطة التوأم {version}"),
    "as.target": ("target utilisation {kind}={value:g}", "نسبة الاستخدام المستهدفة {kind}={value:g}"),
    "as.beds_per_procedure": ("each rescheduled procedure is ASSUMED to free {beds:g} {beds:bed/beds}; this is not simulated and is not subtracted from the confirmed deficit",
                              "يُفترض أن كل عملية مؤجلة تحرر {beds:g} سرير؛ هذا افتراض غير محاكى ولا يُخصم من العجز المؤكد"),
    "as.policy": ("policy {key} = {value:g} (source {source})", "السياسة {key} = {value:g} (المصدر {source})"),
    "as.calendar": ("booking calendar known until {until}; later days are unknown, not free",
                    "جدول الحجوزات معروف حتى {until}؛ الأيام التالية مجهولة وليست متاحة"),
    "unv.no_impact": ("{n} accepted {n:proposal/proposals} {n:has/have} no simulator-verified impact", "{n} اقتراح مقبول بدون أثر محقَّق بالمحاكاة"),
    "unv.no_joint": ("combined impact of the accepted set was not simulated", "الأثر المجمّع للإجراءات المقبولة لم تتم محاكاته"),
    "unv.no_conf": ("forecast confidence not provided", "درجة ثقة التوقع غير متوفرة"),
    "unv.relief": ("{pool}: the accepted postponements are assumed to relieve {relief:g} {relief:bed/beds} of demand; confirmed deficit stays {unmet}, "
                   "and would be {unmet_assumed} only if that assumption holds",
                   "{pool}: يُفترض أن التأجيلات المقبولة تخفف {relief:g} سرير من الطلب؛ العجز المؤكد يبقى {unmet}، "
                   "ويصبح {unmet_assumed} فقط إذا صح هذا الافتراض"),
    "warn.baseline_ratio": ("{unit}: {beds} {beds:bed/beds} / {nurses} {nurses:nurse/nurses} on shift compared with an unapproved ratio "
                            "({limit:g}:1; template ratios are 2:1 ICU / 3:1 ward and neither is approved)",
                            "{unit}: {beds} سرير / {nurses} ممرض في الوردية مقارنةً بنسبة غير معتمدة "
                            "({limit:g}:1؛ النسب النموذجية 2:1 للعناية المركزة و3:1 للداخلي، ولا واحدة منهما معتمدة)"),
    "none.reason.no_proposals": ("No agent proposed an action: there is no forecast shortfall to cover.",
                                 "لم يقترح أي وكيل إجراءً: لا يوجد عجز متوقع يحتاج إلى تغطية."),
    "none.reason.all_rejected": ("{n} {n:proposal/proposals} {n:was/were} rejected by the hard constraints; nothing remains to apply.",
                                 "رُفض {n} اقتراح بسبب القيود الصارمة ولا يوجد ما يمكن تطبيقه."),
    "none.reason.advisory": ("Only advisory alerts were produced; there is nothing to apply to the sandbox.",
                             "صدرت تنبيهات استشارية فقط؛ لا يوجد ما يُطبَّق على بيئة الاختبار."),
    "decision.escalation": ("Unresolved shortfall {beds} {beds:bed/beds}: no verified action can cover it; manager escalation is needed.",
                             "عجز متبقٍ {beds} سرير: لا يغطيه أي إجراء متحقق منه؛ يلزم تصعيده إلى المدير."),
    "stale.sandbox": ("the sandbox changed after this decision was computed", "تغيّرت بيئة الاختبار بعد حساب هذا القرار"),
    "stale.policy": ("a policy changed after this decision was computed", "تغيّرت سياسة بعد حساب هذا القرار"),
    # ───────── what-if page ─────────
    "sim.cost_note": ("Rate arithmetic from cost_rates: converted beds x the destination/source unit's daily bed rate. "
                      "Assumes every converted bed is staffed. It is a calculation, not a simulation, and it excludes postponed procedures.",
                      "حساب بسيط من أسعار التكلفة: الأسرّة المنقولة × السعر اليومي للسرير في الوحدة المستقبِلة/المانحة. "
                      "يفترض أن كل سرير منقول مجهّز بالطاقم. هو حساب وليس محاكاة، ولا يشمل العمليات المؤجلة."),
    "sim.na_wait": ("No simulation engine is connected. The pack's stored ER queue results are not tied to these actions.",
                    "لا يوجد محرك محاكاة متصل. نتائج طابور الطوارئ المخزنة في البيانات غير مرتبطة بهذه الإجراءات."),
    "sim.na_revenue": ("Needs a simulator to value each action; none is connected.", "يحتاج إلى محاكي لتقدير قيمة كل إجراء؛ ولا يوجد محاكي متصل."),
    "sim.na_overtime": ("No staffing demand forecast exists in the data pack.", "لا يوجد توقع لطلب الطاقم في البيانات."),
    "sim.m_wait": ("Waiting time change", "تغيّر زمن الانتظار"),
    "sim.m_revenue": ("Revenue at risk change", "تغيّر الإيراد المعرّض للخطر"),
    "sim.m_overtime": ("Overtime change", "تغيّر العمل الإضافي"),
    "sim.m_relief": ("Effect of postponed procedures on the deficit", "أثر العمليات المؤجلة على العجز"),
    "sim.na_relief": ("Not computed. The confirmed shortfall counts only bed moves; {n} {n:postponement/postponements} {n:is/are} assumed to relieve {relief:g} {relief:bed/beds} "
                      "(assumption, not simulated), shown separately.",
                      "غير محسوب. العجز المؤكد يحتسب نقل الأسرّة فقط؛ يُفترض أن {n} تأجيل يخفف {relief:g} سرير (افتراض وليس محاكاة)، ويُعرض منفصلًا."),
}


class Msg(str):
    """Canonical English text + code + params; renders in any language on demand."""
    code: str
    params: dict

    def __new__(cls, code: str, **params: Any) -> "Msg":
        obj = str.__new__(cls, _fmt(code, 0, params))
        obj.code, obj.params = code, params
        return obj

    def __reduce__(self):
        return (_rebuild, (self.code, self.params))

    def render(self, lang: str = "en") -> str:
        return _fmt(self.code, 1 if lang == "ar" else 0, self.params, lang)


def _rebuild(code: str, params: dict) -> Msg:
    return Msg(code, **params)


def _plain(v: Any, lang: str) -> Any:
    if isinstance(v, Msg):
        return v.render(lang)
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, Msg) for x in v):
        return "; ".join(x.render(lang) for x in v)
    return v


def _fmt(code: str, idx: int, params: dict, lang: str = "en") -> str:
    template = CATALOG.get(code)
    if template is None:
        return code
    p = {k: _plain(v, lang) for k, v in params.items()}
    if idx:                                   # Arabic display names for well-known identifiers
        if "agent" in p:
            p["agent"] = AGENT_AR.get(p["agent"], p["agent"])
    try:
        return format_text(template[idx], **p)
    except (KeyError, IndexError, ValueError):
        return format_text(template[0], **{k: _plain(v, "en") for k, v in params.items()})


def render(x: Any, lang: str = "en") -> str:
    return x.render(lang) if isinstance(x, Msg) else str(x)


def codes(x: Any) -> list[str]:
    """Leaf codes of a message (the wrapper `arb.reason` / `arb.joint` is looked through)."""
    if not isinstance(x, Msg):
        return []
    inner = [c for v in x.params.values() for item in (v if isinstance(v, (list, tuple)) else [v]) for c in codes(item)]
    return inner or [x.code]


def render_all(items: Iterable[Any], lang: str) -> list[str]:
    return [render(i, lang) for i in items]
