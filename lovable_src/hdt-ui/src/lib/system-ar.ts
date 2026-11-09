/** Arabic display labels for English strings the backend returns on the system page (display only). */
export const CHECK_AR: Record<string, [string, string?]> = {
  "Overlapping bed stays": ["تداخل إقامات الأسرة", "نفس السرير مستخدم في إقامتين في نفس الوقت"],
  "Overlapping planned surgeries": ["تداخل العمليات المجدولة", "نفس غرفة العمليات محجوزة مرتين"],
  "Wait longer than length of stay": ["انتظار أطول من مدة الإقامة", "زيارات انتظارها أطول من إقامتها كلها"],
  "Cancelled surgeries with realised margin": ["عمليات ملغاة لها ربح محقق", "العمليات الملغاة لازم يكون ربحها صفر"],
  "ER arrivals match visits": ["تطابق وافدي الطوارئ مع الزيارات", "أيام يختلف فيها daily_metrics عن جدول الزيارات"],
  "Days with unusual staff coverage": ["أيام بتغطية طاقم غير معتادة"],
  "Days without any nurse shift": ["أيام بدون أي وردية تمريض"],
  "Approved policies": ["السياسات المعتمدة", "السياسات في الحزمة أمثلة اصطناعية ولا يوجد منها معتمد"],
  "Decision confidence calibrated": ["معايرة ثقة القرارات", "الثقة فارغة إلى أن يتم معايرة نموذج"],
};

export const FEATURE_AR: Record<string, [string, string]> = {
  "Executive summary wording": ["صياغة الملخص التنفيذي", "تحتاج مفتاح GROQ_API_KEY، ويُستخدم القالب الثابت مؤقتًا."],
  "AI assistant: local answers": ["المساعد: إجابات محلية", "يجيب من بيانات الخادم حسب نوع السؤال مع المصادر، بدون مفتاح."],
  "AI assistant: LLM-assisted answers": ["المساعد: إجابات بالنموذج اللغوي", "يعيد صياغة نفس الأدلة، ويُرفض أي كلام غير مدعوم."],
  "Natural-language what-if questions": ["أسئلة «ماذا لو» باللغة الطبيعية", "غير منفذة. السيناريوهات تُحدد من أدوات التحكم."],
  "Simulation engine (waiting time, queues)": ["محرك المحاكاة (الانتظار والطوابير)", "لا يوجد محرك متصل، وتُعرض نتائج الحزمة المخزنة كمرجع فقط."],
  "Source search (BM25, Arabic and English)": ["البحث في المصادر (عربي وإنجليزي)", "يعمل محليًا على المصادر وسياسات الحزمة."],
  "Constraint checking and arbitration": ["فحص القيود والتحكيم", "ثابت ويعمل محليًا."],
};

export function checkLabel(lang: string, name: string, detail: string) {
  if (lang !== "ar") return { name, detail };
  const m = name.match(/^(\w+) count matches validation_report\.json$/);
  let d = detail
    .replace(/^report says (\d+), CSV has (\d+)$/, "التقرير يقول $1، وملف CSV فيه $2")
    .replace(/^Shifts per day vs median (\d+):/, "الورديات في اليوم مقارنة بالوسيط $1:")
    .replace(/ has (\d+)/g, " فيه $1")
    .replace(/^Days with no present nurse per unit:/, "أيام بدون ممرض حاضر لكل قسم:");
  const ar = CHECK_AR[name];
  if (ar?.[1]) d = ar[1];
  return { name: m ? `عدد ${m[1]} يطابق تقرير التحقق` : ar?.[0] ?? name, detail: d };
}

export function featureLabel(lang: string, name: string, note: string) {
  const ar = lang === "ar" ? FEATURE_AR[name] : undefined;
  if (ar && /^Needs GROQ_API_KEY\.?$/.test(note)) return { name: ar[0], note: "يحتاج مفتاح GROQ_API_KEY." };
  return { name: ar?.[0] ?? name, note: ar?.[1] ?? note };
}
