/**
 * Grid Impact Tracker: resident bill submissions.
 *
 * Container-bound to a private Google Sheet owned by the project owner.
 * - setup() (run once from the "Grid Impact" menu) creates the Google Form and links its
 *   responses to this spreadsheet. It never deletes anything.
 * - doGet() is a public web app that returns ONLY aggregate figures:
 *     pending:   exact count of valid bills per ZIP code (last 12 months) below the threshold
 *     published: for ZIP codes with at least THRESHOLD valid bills, the count and medians
 *   Individual responses are never returned.
 * No names, emails, addresses, account numbers, or files are collected.
 *
 * Site feedback ("Report an issue" on every page): setupFeedback() creates a second form whose
 * answers go to the private "Feedback (private)" tab. doGet() returns only the number of reports,
 * so the pipeline can notify the owner; report text never leaves the sheet.
 */
const THRESHOLD = 10;
const WINDOW_DAYS = 365;
const TITLE = "Grid Impact Tracker: share your electric bill";
const RESPONSES_SHEET = "Responses (private)";
const Q = {
  zip: "ZIP code",
  utility: "Electric utility",
  date: "Bill statement date",
  kwh: "Electricity used on this bill (kWh)",
  total: "Total amount of this bill ($)",
  days: "Days in the billing period",
  supply: "Who supplies your electricity?",
  heat: "Do you heat your home mainly with electricity?",
  consent: "Consent",
  supply: "Supply charges ($)",
  delivery: "Delivery charges ($)",
  fixed: "Fixed customer charge ($)",
  taxes: "Taxes and other fees ($)",
};
const BREAKDOWN_HEADER = "Cost breakdown (optional)";
const EXCLUDE_HEADER = "Exclude (owner use)";  // any value in this column removes the row from all counts
const BREAKDOWN_TOLERANCE = 0.08;  // supply + delivery + taxes must be within 8% of the total
const FEEDBACK_TITLE = "Grid Impact Tracker: report an issue";
const FEEDBACK_SHEET = "Feedback (private)";
const FQ = {
  page: "Which page?",
  kind: "What kind of issue?",
  details: "What did you see?",
  where: "Place, utility, or data center (optional)",
  email: "Email (optional)",
};
const SITE_PAGES = ["Map", "Findings", "Your utility", "Methods", "References", "Data status", "Other"];
const SUGGEST_REFERENCE = "Suggest a reference (study, filing, or news story)";

function onOpen() {
  SpreadsheetApp.getUi().createMenu("Grid Impact")
    .addItem("Set up form (run once)", "setup")
    .addItem("Add cost breakdown questions", "addCostBreakdown")
    .addItem("Add exclude column", "addExcludeColumn")
    .addItem("Set up feedback form", "setupFeedback")
    .addItem("Show form and data links", "showLinks")
    .addToUi();
}

function setup() {
  const props = PropertiesService.getScriptProperties();
  const ui = SpreadsheetApp.getUi();
  if (props.getProperty("formId")) {
    ui.alert("Already set up. Use Grid Impact > Show form and data links.");
    return;
  }
  const ss = SpreadsheetApp.getActive();
  const form = FormApp.create(TITLE);
  form.setDescription(
    "Help measure how electricity costs are changing near data centers. Share the numbers from one recent " +
    "electric bill. We do not collect your name, email, address, or account number.\n\n" +
    "How your answers are used: answers are stored privately by the Grid Impact Tracker project " +
    "(https://yottachem.github.io/grid-impact/). The public site shows how many bills each ZIP code has received, " +
    "and once a ZIP code has at least " + THRESHOLD + " bills from the past 12 months, it shows the typical (median) " +
    "bill, usage, and price for that ZIP code. Individual answers are never published.");
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);
  form.setConfirmationMessage("Thank you. Your bill counts toward your ZIP code's total on the Grid Impact Tracker. " +
    "Results appear once " + THRESHOLD + " bills from your ZIP code are in.");

  const num = (lo, hi, help) => FormApp.createTextValidation().requireNumberBetween(lo, hi).setHelpText(help).build();
  form.addTextItem().setTitle(Q.zip).setHelpText("5-digit ZIP code where the bill is for").setRequired(true)
    .setValidation(FormApp.createTextValidation().requireTextMatchesPattern("^[0-9]{5}$").setHelpText("Enter a 5-digit ZIP code").build());
  form.addTextItem().setTitle(Q.utility).setHelpText("As shown on your bill, for example Dominion Energy Virginia").setRequired(true);
  form.addDateItem().setTitle(Q.date).setHelpText("The date printed on the bill").setRequired(true);
  form.addTextItem().setTitle(Q.kwh).setHelpText("Usually labeled kWh used or total usage").setRequired(true)
    .setValidation(num(1, 20000, "Enter a number of kWh"));
  form.addTextItem().setTitle(Q.total).setHelpText("Total for electricity on this bill, in dollars").setRequired(true)
    .setValidation(num(1, 5000, "Enter a dollar amount, numbers only"));
  form.addTextItem().setTitle(Q.days).setHelpText("Optional. Usually about 30").setRequired(false)
    .setValidation(num(1, 100, "Enter a number of days"));
  form.addMultipleChoiceItem().setTitle(Q.supply).setRequired(false)
    .setChoiceValues(["My utility (standard or default service)", "A different supplier or retail electricity provider", "Not sure"]);
  form.addMultipleChoiceItem().setTitle(Q.heat).setRequired(false).setChoiceValues(["Yes", "No", "Not sure"]);
  form.addCheckboxItem().setTitle(Q.consent).setRequired(true)
    .setChoiceValues(["I agree that these bill numbers can be used in aggregate as described above. I have not entered my name, address, or account number."]);

  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  SpreadsheetApp.flush();
  // Rename the linked responses tab (it is the sheet whose form URL matches)
  const sheet = ss.getSheets().find(s => s.getFormUrl && s.getFormUrl());
  if (sheet) sheet.setName(RESPONSES_SHEET);

  props.setProperties({ formId: form.getId(), formUrl: form.getPublishedUrl(), spreadsheetId: ss.getId() });
  ui.alert("Form created.\n\nForm link: " + form.getPublishedUrl());
}

/**
 * Adds optional supply / delivery / fixed charge / taxes questions after "Total amount".
 * Idempotent: skips questions that already exist. Never deletes or edits existing questions.
 */
function addCostBreakdown() {
  const ui = SpreadsheetApp.getUi();
  const added = addCostBreakdown_();
  if (added === null) { ui.alert("Run Grid Impact > Set up form first."); return; }
  ui.alert(added.length ? "Added: " + added.join(", ") : "Cost breakdown questions are already on the form.");
}

/** Core of addCostBreakdown without UI. Returns titles added, or null if the form isn't set up. */
function addCostBreakdown_() {
  const p = PropertiesService.getScriptProperties();
  const formId = p.getProperty("formId");
  if (!formId) return null;
  const form = FormApp.openById(formId);
  const titles = new Set(form.getItems().map(i => i.getTitle()));
  const totalIdx = form.getItems().findIndex(i => i.getTitle() === Q.total);
  let at = totalIdx >= 0 ? totalIdx + 1 : form.getItems().length;
  const added = [];
  const place = item => { form.moveItem(item.getIndex(), at); at += 1; };
  const money = help => FormApp.createTextValidation().requireNumberBetween(0, 5000).setHelpText(help).build();
  if (!titles.has(BREAKDOWN_HEADER)) {
    place(form.addSectionHeaderItem().setTitle(BREAKDOWN_HEADER).setHelpText(
      "If your bill splits the total, enter the parts. Supply is the cost of the electricity itself; delivery is the cost " +
      "of the wires and grid that bring it to you. Data center growth can raise either one, so the split shows which. " +
      "Leave these blank if your bill doesn't break them out."));
    added.push(BREAKDOWN_HEADER);
  }
  const items = [
    [Q.supply, "Often labeled Supply, Generation, Energy charges, or your retail electricity provider's charges"],
    [Q.delivery, "Often labeled Delivery, Distribution, Transmission, or your utility's or wires company's charges. Include the fixed customer charge and riders"],
    [Q.fixed, "The flat monthly charge you pay no matter how much you use (Customer charge, Basic service charge). It is part of delivery"],
    [Q.taxes, "Taxes, surcharges, and fees listed separately from supply and delivery"],
  ];
  items.forEach(([title, help]) => {
    if (titles.has(title)) return;
    place(form.addTextItem().setTitle(title).setHelpText(help).setRequired(false).setValidation(money("Enter a dollar amount, numbers only")));
    added.push(title);
  });
  return added;
}

/** Adds an "Exclude (owner use)" column to the responses tab. Never edits or deletes responses. */
function addExcludeColumn() {
  const r = addExcludeColumn_();
  SpreadsheetApp.getUi().alert(r.added ? "Added column \"" + EXCLUDE_HEADER + "\" to " + r.tab + ". Type x in a row to exclude it." :
    "The exclude column already exists in " + r.tab + ".");
}

function responsesTab_(ss) {
  // The tab with the form's columns that holds the most responses. Google can start a new tab
  // (e.g. "Form Responses 1") after the form changes; neither tab is renamed or deleted.
  const tabs = ss.getSheets().filter(sh => sh.getLastColumn() > 0 &&
    sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].indexOf(Q.zip) >= 0);
  tabs.sort((a, b) => (b.getLastRow() - a.getLastRow()) || (b.getLastColumn() - a.getLastColumn()));
  return tabs[0];
}

function addExcludeColumn_() {
  const ss = SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty("spreadsheetId"));
  const sh = responsesTab_(ss);
  const head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  if (head.indexOf(EXCLUDE_HEADER) >= 0) return { added: false, tab: sh.getName() };
  sh.getRange(1, sh.getLastColumn() + 1).setValue(EXCLUDE_HEADER).setNote("Type x (or anything) to leave this row out of all public counts. Rows are never deleted.");
  return { added: true, tab: sh.getName() };
}

/** Creates the site feedback form (once). Never deletes or edits anything existing. */
function setupFeedback() {
  const r = setupFeedback_();
  SpreadsheetApp.getUi().alert((r.created ? "Feedback form created.\n\n" : "Feedback form already exists.\n\n") + "Form link: " + r.url);
}

function setupFeedback_() {
  const p = PropertiesService.getScriptProperties();
  if (p.getProperty("feedbackFormId")) return { created: false, url: p.getProperty("feedbackFormUrl"), entry: p.getProperty("feedbackPageEntry") };
  const ssId = p.getProperty("spreadsheetId");
  const before = new Set(SpreadsheetApp.openById(ssId).getSheets().map(sh => sh.getSheetId()));
  const form = FormApp.create(FEEDBACK_TITLE);
  form.setDescription(
    "Tell us about a wrong or outdated figure, a data center that is missing or listed twice, a conclusion you " +
    "disagree with, or anything on the site that is broken or confusing.\n\n" +
    "Reports go privately to the Grid Impact Tracker project (https://yottachem.github.io/grid-impact/) and are " +
    "never published. An email address is optional and used only to reply.");
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);
  form.setConfirmationMessage("Thank you. Your report goes privately to the project owner; nothing you entered is published.");
  const page = form.addListItem().setTitle(FQ.page).setChoiceValues(SITE_PAGES).setRequired(true);
  form.addMultipleChoiceItem().setTitle(FQ.kind).setRequired(true).setChoiceValues([
    "A figure is wrong, missing, or out of date",
    "A data center is missing, duplicated, or wrong",
    "I disagree with a conclusion",
    "Something is broken or hard to use",
    "Suggestion",
    SUGGEST_REFERENCE,
    "Other"]);
  form.addParagraphTextItem().setTitle(FQ.details).setRequired(true)
    .setHelpText("What you saw, and what you think is right. Include a source if you have one (filing, news article, operator website).");
  form.addTextItem().setTitle(FQ.where).setRequired(false).setHelpText("For example: Loudoun County, VA; Dominion Energy; or a data center's name");
  form.addTextItem().setTitle(FQ.email).setRequired(false).setHelpText("Only if you would like a reply. Kept private.")
    .setValidation(FormApp.createTextValidation().requireTextIsEmail().setHelpText("Enter an email address, or leave this blank").build());
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ssId);
  SpreadsheetApp.flush();
  const tab = SpreadsheetApp.openById(ssId).getSheets().find(sh => !before.has(sh.getSheetId()));
  if (tab) tab.setName(FEEDBACK_SHEET);
  // Entry ID of the page question, so each site page can link to the form with its name filled in
  const pre = form.createResponse().withItemResponse(page.createResponse("Map")).toPrefilledUrl();
  const entry = (pre.match(/entry\.(\d+)=/) || [])[1] || "";
  p.setProperties({ feedbackFormId: form.getId(), feedbackFormUrl: form.getPublishedUrl(), feedbackPageEntry: entry });
  return { created: true, url: form.getPublishedUrl(), entry: entry };
}

/** Adds new page and issue-type choices to an existing feedback form. Keeps every existing choice. */
function updateFeedbackChoices_() {
  const id = PropertiesService.getScriptProperties().getProperty("feedbackFormId");
  if (!id) return { updated: false };
  const form = FormApp.openById(id);
  const added = [];
  form.getItems().forEach(item => {
    const t = item.getTitle();
    if (t === FQ.page) {
      const li = item.asListItem(), have = li.getChoices().map(c => c.getValue());
      const want = SITE_PAGES.filter(v => have.indexOf(v) < 0);
      if (want.length) {
        // keep existing order, insert new pages before "Data status"/"Other"
        const merged = SITE_PAGES.filter(v => have.indexOf(v) >= 0 || want.indexOf(v) >= 0).concat(have.filter(v => SITE_PAGES.indexOf(v) < 0));
        li.setChoiceValues(merged); added.push(...want);
      }
    }
    if (t === FQ.kind) {
      const mc = item.asMultipleChoiceItem(), have = mc.getChoices().map(c => c.getValue());
      if (have.indexOf(SUGGEST_REFERENCE) < 0) {
        const i = have.indexOf("Other");
        const merged = i >= 0 ? have.slice(0, i).concat([SUGGEST_REFERENCE], have.slice(i)) : have.concat([SUGGEST_REFERENCE]);
        mc.setChoiceValues(merged); added.push(SUGGEST_REFERENCE);
      }
    }
  });
  return { updated: added.length > 0, added: added };
}

/** Number of feedback reports (no content). */
function feedbackCount_() {
  const p = PropertiesService.getScriptProperties();
  if (!p.getProperty("feedbackFormId")) return null;
  const ss = SpreadsheetApp.openById(p.getProperty("spreadsheetId"));
  const tab = ss.getSheetByName(FEEDBACK_SHEET) || ss.getSheets().find(sh => sh.getLastColumn() > 0 &&
    sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].indexOf(FQ.details) >= 0);
  return { form_url: p.getProperty("feedbackFormUrl"), page_entry: p.getProperty("feedbackPageEntry"),
           total: tab ? Math.max(0, tab.getLastRow() - 1) : 0 };
}

function showLinks() {
  const p = PropertiesService.getScriptProperties();
  SpreadsheetApp.getUi().alert("Form: " + (p.getProperty("formUrl") || "not set up yet"));
}

function median_(xs) {
  const s = xs.slice().sort((a, b) => a - b), n = s.length;
  return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null;
}

function aggregates_() {
  const p = PropertiesService.getScriptProperties();
  const ss = SpreadsheetApp.openById(p.getProperty("spreadsheetId"));
  // Responses tab: the tab with the form's columns that holds the most responses. Google can
  // start a new tab (e.g. "Form Responses 1") after the form changes, leaving an older,
  // empty one behind; neither is renamed or deleted.
  const sheet = responsesTab_(ss);
  const out = { threshold: THRESHOLD, window_days: WINDOW_DAYS, updated: new Date().toISOString(),
                form_url: p.getProperty("formUrl"), pending: [], published: [], invalid: 0, excluded: 0, total: 0 };
  out.feedback = feedbackCount_();
  if (!sheet) return out;
  const rows = sheet.getDataRange().getValues();
  const head = rows.shift() || [];
  const col = name => head.indexOf(name);
  const cutoff = new Date(Date.now() - WINDOW_DAYS * 86400000);
  const byZip = {};
  rows.forEach(r => {
    if (col(EXCLUDE_HEADER) >= 0 && String(r[col(EXCLUDE_HEADER)]).trim() !== "") { out.excluded++; return; }
    out.total++;
    const zip = String(r[col(Q.zip)]).padStart(5, "0");
    const kwh = Number(r[col(Q.kwh)]), total = Number(r[col(Q.total)]);
    const days = Number(r[col(Q.days)]) || 30;
    const date = new Date(r[col(Q.date)]);
    const cents = kwh > 0 ? total * 100 / kwh : NaN;
    // Plausibility checks: monthly-equivalent usage and an implied price between 5 and 80 cents/kWh
    const monthlyKwh = kwh * 30 / days;
    const valid = /^[0-9]{5}$/.test(zip) && date >= cutoff && date <= new Date() &&
      monthlyKwh >= 50 && monthlyKwh <= 8000 && cents >= 5 && cents <= 80;
    if (!valid) { out.invalid++; return; }
    const num = name => { const i = col(name); const v = i >= 0 ? Number(r[i]) : NaN; return r[i] === "" ? NaN : v; };
    const supply = num(Q.supply), delivery = num(Q.delivery), fixed = num(Q.fixed), taxes = num(Q.taxes);
    // If only supply or only delivery is given, derive the other from the total (minus taxes if given)
    const tx = isNaN(taxes) ? 0 : taxes;
    let sup = supply, del = delivery, derived = false;
    if (sup >= 0 && isNaN(del)) { del = total - sup - tx; derived = true; }
    else if (del >= 0 && isNaN(sup)) { sup = total - del - tx; derived = true; }
    const split = sup >= 0 && del >= 0 && (derived || Math.abs(sup + del + tx - total) <= BREAKDOWN_TOLERANCE * total);
    const k = 30 / days;
    (byZip[zip] = byZip[zip] || []).push({ kwh: monthlyKwh, bill: total * k, cents,
      split, derived: split && derived, supply_cents: split ? sup * 100 / kwh : null, delivery_cents: split ? del * 100 / kwh : null,
      fees_share: split && !isNaN(taxes) ? taxes / total : null, fixed: split && fixed >= 0 ? fixed * k : null });
  });
  Object.keys(byZip).sort().forEach(zip => {
    const b = byZip[zip];
    if (b.length >= THRESHOLD) {
      const rec = { zip, n: b.length,
        median_monthly_bill: Math.round(median_(b.map(x => x.bill))),
        median_monthly_kwh: Math.round(median_(b.map(x => x.kwh))),
        median_cents_per_kwh: Math.round(median_(b.map(x => x.cents)) * 10) / 10 };
      const sp = b.filter(x => x.split);
      rec.n_breakdown = sp.length;
      rec.n_breakdown_derived = sp.filter(x => x.derived).length;
      if (sp.length >= THRESHOLD) {
        const r1 = v => Math.round(v * 10) / 10;
        rec.median_supply_cents_per_kwh = r1(median_(sp.map(x => x.supply_cents)));
        rec.median_delivery_cents_per_kwh = r1(median_(sp.map(x => x.delivery_cents)));
        const fx = sp.filter(x => x.fixed != null), fs = sp.filter(x => x.fees_share != null);
        if (fx.length >= THRESHOLD) rec.median_fixed_charge = Math.round(median_(fx.map(x => x.fixed)) * 100) / 100;
        if (fs.length >= THRESHOLD) rec.median_taxes_fees_share = Math.round(median_(fs.map(x => x.fees_share)) * 1000) / 1000;
      }
      out.published.push(rec);
    } else {
      out.pending.push({ zip, n: b.length, n_breakdown: b.filter(x => x.split).length });  // derived splits included
    }
  });
  return out;
}

function doGet() {
  return ContentService.createTextOutput(JSON.stringify(aggregates_())).setMimeType(ContentService.MimeType.JSON);
}
