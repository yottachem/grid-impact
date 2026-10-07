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
};

function onOpen() {
  SpreadsheetApp.getUi().createMenu("Grid Impact")
    .addItem("Set up form (run once)", "setup")
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
  const sheet = ss.getSheetByName(RESPONSES_SHEET);
  const out = { threshold: THRESHOLD, window_days: WINDOW_DAYS, updated: new Date().toISOString(),
                form_url: p.getProperty("formUrl"), pending: [], published: [], invalid: 0, total: 0 };
  if (!sheet) return out;
  const rows = sheet.getDataRange().getValues();
  const head = rows.shift() || [];
  const col = name => head.indexOf(name);
  const cutoff = new Date(Date.now() - WINDOW_DAYS * 86400000);
  const byZip = {};
  rows.forEach(r => {
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
    (byZip[zip] = byZip[zip] || []).push({ kwh: monthlyKwh, bill: total * 30 / days, cents });
  });
  Object.keys(byZip).sort().forEach(zip => {
    const b = byZip[zip];
    if (b.length >= THRESHOLD) {
      out.published.push({ zip, n: b.length,
        median_monthly_bill: Math.round(median_(b.map(x => x.bill))),
        median_monthly_kwh: Math.round(median_(b.map(x => x.kwh))),
        median_cents_per_kwh: Math.round(median_(b.map(x => x.cents)) * 10) / 10 });
    } else {
      out.pending.push({ zip, n: b.length });
    }
  });
  return out;
}

function doGet() {
  return ContentService.createTextOutput(JSON.stringify(aggregates_())).setMimeType(ContentService.MimeType.JSON);
}
