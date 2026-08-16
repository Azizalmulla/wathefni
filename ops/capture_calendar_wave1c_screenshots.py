#!/usr/bin/env python3
"""Capture Calendar Wave 1c visual-closure screenshots (EN/AR, dense/sparse, drawer/sheet)."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

STAMP = Path("/tmp/cal-w1c-stamp.txt").read_text().strip()
OUT = Path(f"/Users/azizalmulla/Desktop/claw/ops/evidence/calendar-wave1c-visual-closure-prod-deploy-{STAMP}/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
HTML = OUT.parent / "preview" / "wave1c-visual-fixture.html"
HTML.parent.mkdir(parents=True, exist_ok=True)

FIXTURE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Calendar Wave 1c visual fixture</title>
<style>
  :root {
    --ink: #231f1b; --muted: #71685b; --line: #ded3c1; --panel: #fbf7ee;
    --follow: #d9e7f5; --follow-ink: #2a4a6a; --review: #f5e7c8; --review-ink: #6a4a18;
    --paused: #e8e2d8; --paused-ink: #4a4338; --frame: #f3ebe0; --surface: #fffaf0;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Iowan Old Style", "Palatino Linotype", Palatino, serif; background: #f4eee4; color: var(--ink); }
  .shell { max-width: 1180px; margin: 0 auto; padding: 16px 20px 40px; }
  .title { font-size: 1.75rem; font-weight: 650; letter-spacing: -0.03em; margin: 0; }
  .sub { margin: 4px 0 10px; color: var(--muted); font-size: 13px; max-width: 36rem; }
  .refresh { float: right; width: 32px; height: 32px; border-radius: 999px; border: 1px solid #e2d7c6; background: #fff; color: var(--muted); font-size: 14px; }
  .banner { display: inline-flex; align-items: center; gap: 8px; border: 1px solid rgba(106,74,24,.35); background: rgba(245,231,200,.55); color: var(--review-ink); border-radius: 999px; padding: 4px 12px; font-size: 11px; font-weight: 600; margin-bottom: 10px; }
  .banner i { width: 6px; height: 6px; border-radius: 99px; background: var(--review-ink); opacity: .7; display: inline-block; }
  .toolbar, .filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; border: 1px solid rgba(222,211,193,.7); background: rgba(255,250,240,.9); border-radius: 1.35rem; padding: 8px; margin-bottom: 8px; }
  .pill { display: inline-flex; background: #f3ebe0; border-radius: 999px; padding: 4px; }
  .pill button, .scope button { border: 0; background: transparent; border-radius: 999px; padding: 6px 12px; font: inherit; font-size: 13px; color: var(--muted); cursor: pointer; }
  .pill button.on, .scope button.on { background: var(--ink); color: #fff; }
  .scope { margin-inline-start: auto; display: inline-flex; background: #f3ebe0; border-radius: 999px; padding: 4px; }
  .board { border: 1px solid #ded3c1; background: var(--panel); border-radius: 1.55rem; overflow: hidden; box-shadow: 0 14px 34px rgba(35,33,29,.055); position: relative; min-height: 520px; }
  .week-head, .week-grid { display: grid; grid-template-columns: 64px repeat(7, minmax(0,1fr)); min-width: 720px; }
  .week-head { background: #f7f0e4; border-bottom: 1px solid #ded3c1; }
  .week-head div { text-align: center; padding: 12px 8px; font-size: 12px; font-weight: 650; color: var(--muted); border-inline-start: 1px solid #e5dac9; }
  .week-grid { position: relative; height: 432px; }
  .gutter { border-inline-end: 1px solid #ded3c1; background: rgba(247,240,228,.65); position: relative; }
  .gutter span { position: absolute; inset-inline: 0; padding: 4px 8px; font-size: 11px; color: #71685b; border-top: 1px solid #ded3c1; }
  .daycol { position: relative; border-inline-start: 1px solid #ded3c1; background: rgba(255,250,240,.55); }
  .ev { position: absolute; border-radius: .8rem; border: 1px solid transparent; padding: 6px; font-size: 11px; overflow: hidden; box-shadow: 0 2px 8px rgba(35,33,29,.07); }
  .ev .dot { width: 3px; height: 12px; border-radius: 99px; background: rgba(106,74,24,.55); display: inline-block; margin-inline-end: 4px; vertical-align: middle; }
  .ev .t { font-weight: 650; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .ev .tm { opacity: .7; font-size: 9px; margin-top: 2px; }
  .interview { background: var(--follow); color: var(--follow-ink); }
  .deadline { background: var(--review); color: var(--review-ink); }
  .leave { background: var(--paused); color: var(--paused-ink); }
  .meeting { background: var(--frame); color: var(--ink); }
  .month { display: grid; grid-template-columns: repeat(7, 1fr); gap: 1px; background: #e8dfd0; }
  .mcell { min-height: 96px; background: var(--surface); padding: 8px; text-align: start; font-size: 12px; }
  .mcell .chip { display: flex; gap: 4px; align-items: start; border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 600; line-height: 1.25; margin-top: 4px; }
  .mcell .chip span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .agenda { padding: 10px 12px; border-bottom: 1px solid #e2d7c6; }
  .agenda h3 { margin: 0 0 6px; font-size: 13px; }
  .acard { border-radius: 12px; border: 1px solid transparent; padding: 6px 10px; margin-bottom: 6px; }
  .empty { color: var(--muted); font-size: 12px; padding: 4px 0; }
  .overlay { position: absolute; inset: 0; background: rgba(35,33,29,.25); backdrop-filter: blur(1px); }
  .drawer { position: absolute; inset-block: 0; inset-inline-end: 0; width: min(380px, 100%); background: #fff; border-inline-start: 1px solid rgba(222,211,193,.55); padding: 16px; box-shadow: -18px 0 40px rgba(35,33,29,.12); overflow: auto; }
  .sheet { position: absolute; inset-inline: 0; bottom: 0; max-height: 70%; background: #fff; border-radius: 1.55rem 1.55rem 0 0; padding: 16px; box-shadow: 0 -18px 40px rgba(35,33,29,.14); }
  .cat { font-size: 11px; letter-spacing: .16em; text-transform: uppercase; color: var(--muted); }
  .honesty { font-size: 11px; font-weight: 650; color: var(--review-ink); margin-top: 4px; }
  .mobile .board { min-height: 640px; }
  [dir=rtl] .drawer { inset-inline-end: auto; inset-inline-start: 0; border-inline-start: 0; border-inline-end: 1px solid rgba(222,211,193,.55); box-shadow: 18px 0 40px rgba(35,33,29,.12); }
  .hidden { display: none !important; }
  .view-month .week-wrap, .view-day .week-wrap, .view-week .month, .view-day .month, .view-week .day-agenda, .view-month .day-agenda { display: none; }
  .view-week .week-wrap, .view-month .month, .view-day .day-agenda { display: block; }
  .view-month .month { display: grid; }
</style>
</head>
<body>
  <div class="shell" id="app">
    <button class="refresh" title="Refresh" aria-label="Refresh">↻</button>
    <h1 class="title" id="pageTitle">Calendar</h1>
    <p class="sub" id="pageSub">Day, week, and month for your schedule and hiring team.</p>
    <div class="banner" data-calendar-populated-preview-banner><i></i><span id="bannerText">WATHEFNI canary preview — synthetic events for review only · 9</span></div>
    <div class="toolbar">
      <div class="pill" id="viewPill">
        <button data-v="day">Day</button>
        <button data-v="week" class="on">Week</button>
        <button data-v="month">Month</button>
      </div>
      <strong id="rangeLabel">Aug 2 – Aug 8, 2026</strong>
      <div class="scope"><button class="on">My calendar</button><button>Hiring team</button><button>Company calendar</button></div>
    </div>
    <div class="filters"><span style="font-size:13px;color:var(--muted)">All types · All statuses</span></div>
    <div class="board view-week" id="board">
      <div class="week-wrap">
        <div class="week-head">
          <div></div>
          <div>Sun<br><span style="display:inline-grid;place-items:center;width:28px;height:28px;border-radius:99px;margin-top:4px;color:var(--ink)">2</span></div>
          <div>Mon<br><span style="display:inline-grid;place-items:center;width:28px;height:28px;border-radius:99px;margin-top:4px;color:var(--ink)">3</span></div>
          <div>Tue<br><span style="display:inline-grid;place-items:center;width:28px;height:28px;border-radius:99px;margin-top:4px;color:var(--ink)">4</span></div>
          <div>Wed<br><span style="display:inline-grid;place-items:center;width:28px;height:28px;border-radius:99px;margin-top:4px;color:var(--ink)">5</span></div>
          <div>Thu<br><span style="display:inline-grid;place-items:center;width:28px;height:28px;border-radius:99px;margin-top:4px;color:#fff;background:#c89445">6</span></div>
          <div>Fri<br><span style="display:inline-grid;place-items:center;width:28px;height:28px;border-radius:99px;margin-top:4px;color:var(--ink)">7</span></div>
          <div>Sat<br><span style="display:inline-grid;place-items:center;width:28px;height:28px;border-radius:99px;margin-top:4px;color:var(--ink)">8</span></div>
        </div>
        <div class="week-grid">
          <div class="gutter">
            <span style="top:0">7 AM</span><span style="top:48px">8 AM</span><span style="top:96px">9 AM</span>
            <span style="top:144px">10 AM</span><span style="top:192px">11 AM</span><span style="top:240px">12 PM</span>
            <span style="top:288px">1 PM</span><span style="top:336px">2 PM</span><span style="top:384px">3 PM</span>
          </div>
          <div class="daycol"></div>
          <div class="daycol">
            <div class="ev interview" style="top:144px;height:48px;inset-inline-start:3px;width:calc(50% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Interview · Sara · Product Designer</div><div class="tm">10:00 – 11:00</div></div>
            <div class="ev meeting" style="top:168px;height:48px;inset-inline-start:calc(50% + 3px);width:calc(50% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Meeting · Hiring sync</div><div class="tm">10:30 – 11:30</div></div>
          </div>
          <div class="daycol">
            <div class="ev interview" style="top:336px;height:48px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Interview · Omar · Ops Lead</div><div class="tm">2:00 – 3:00</div></div>
            <div class="ev deadline" style="top:384px;height:28px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Payroll cutoff</div><div class="tm">4:00 – 4:30</div></div>
          </div>
          <div class="daycol">
            <div class="ev interview" style="top:96px;height:36px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Video interview · Lina</div><div class="tm">9:00 – 9:45</div></div>
            <div class="ev leave" style="top:0;height:28px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Approved leave · Nour</div><div class="tm">All day</div></div>
          </div>
          <div class="daycol">
            <div class="ev leave" style="top:0;height:28px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Approved leave · Nour</div><div class="tm">All day</div></div>
            <div class="ev deadline" style="top:216px;height:28px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Follow-up · Sara</div><div class="tm">11:30 – 12:00</div></div>
            <div class="ev meeting" style="top:288px;height:96px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Training · Safety</div><div class="tm">1:00 – 3:00</div></div>
          </div>
          <div class="daycol">
            <div class="ev interview" style="top:192px;height:48px;inset-inline:3px;width:calc(100% - 6px);opacity:.65" data-preview-only="true"><span class="dot"></span><div class="t">Interview · cancelled slot</div><div class="tm">11:00 – 12:00</div></div>
            <div class="ev deadline" style="top:384px;height:28px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Onboarding · docs due</div><div class="tm">5:00 – 5:30</div></div>
          </div>
          <div class="daycol">
            <div class="ev deadline" style="top:96px;height:28px;inset-inline:3px;width:calc(100% - 6px)" data-preview-only="true"><span class="dot"></span><div class="t">Compliance · Civil ID</div><div class="tm">9:00 – 9:30</div></div>
          </div>
        </div>
      </div>
      <div class="month hidden">
        <div class="mcell"><strong>2</strong><div class="empty">—</div></div>
        <div class="mcell"><strong>3</strong>
          <div class="chip interview" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Interview · Sara · Product Designer</span></div>
          <div class="chip meeting" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Meeting · Hiring sync</span></div>
        </div>
        <div class="mcell"><strong>4</strong>
          <div class="chip interview" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Interview · Omar · Ops Lead</span></div>
          <div class="chip deadline" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Payroll cutoff</span></div>
        </div>
        <div class="mcell"><strong>5</strong>
          <div class="chip leave" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Approved leave · Nour</span></div>
          <div class="chip interview" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Video interview · Lina</span></div>
        </div>
        <div class="mcell"><strong>6</strong>
          <div class="chip deadline" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Follow-up · Sara</span></div>
          <div class="chip meeting" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Training · Safety</span></div>
        </div>
        <div class="mcell"><strong>7</strong>
          <div class="chip interview" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Interview · cancelled slot</span></div>
        </div>
        <div class="mcell"><strong>8</strong>
          <div class="chip deadline" data-preview-only="true"><i class="dot" style="width:6px;height:6px;border-radius:99px;background:rgba(106,74,24,.6);margin-top:3px;flex:none"></i><span>Compliance · Civil ID</span></div>
        </div>
      </div>
      <div class="day-agenda hidden">
        <div class="agenda"><h3 id="sparseDayHead">Sunday, Aug 2</h3><p class="empty">No events</p></div>
        <div class="agenda"><h3>Monday, Aug 3</h3>
          <div class="acard interview" data-preview-only="true"><span class="dot"></span><div class="t">Interview · Sara · Product Designer</div><div class="tm">10:00 – 11:00</div></div>
          <div class="acard meeting" data-preview-only="true"><span class="dot"></span><div class="t">Meeting · Hiring sync</div><div class="tm">10:30 – 11:30</div></div>
        </div>
      </div>
      <div id="overlay" class="overlay hidden"></div>
      <aside id="drawer" class="drawer hidden" data-calendar-detail-drawer data-calendar-detail-mode="side">
        <div class="cat">Category · Interview</div>
        <h2 style="margin:4px 0 0;font-size:1.15rem">Interview · Sara · Product Designer</h2>
        <p class="honesty" data-calendar-preview-only>Preview only — not a real record in any module.</p>
        <p style="font-size:13px;margin-top:12px"><span style="color:var(--muted);font-size:11px">When</span><br>Mon 10:00 → 11:00 · Asia/Kuwait</p>
        <p style="font-size:13px"><span style="color:var(--muted);font-size:11px">Status</span><br>Confirmed</p>
      </aside>
      <aside id="sheet" class="sheet hidden" data-calendar-detail-drawer data-calendar-detail-mode="sheet">
        <div class="cat">Category · Interview</div>
        <h2 style="margin:4px 0 0;font-size:1.1rem">Interview · Sara · Product Designer</h2>
        <p class="honesty">Preview only — not a real record in any module.</p>
      </aside>
    </div>
  </div>
<script>
const board = document.getElementById('board');
const pills = [...document.querySelectorAll('#viewPill button')];
function setView(v){
  pills.forEach(b => b.classList.toggle('on', b.dataset.v===v));
  board.classList.remove('view-day','view-week','view-month');
  board.classList.add('view-'+v);
  board.querySelector('.week-wrap').classList.toggle('hidden', v!=='week');
  board.querySelector('.month').classList.toggle('hidden', v!=='month');
  board.querySelector('.day-agenda').classList.toggle('hidden', v!=='day');
}
pills.forEach(b => b.onclick = () => setView(b.dataset.v));
window.__cal = {
  setView,
  openDrawer(){ overlay.classList.remove('hidden'); drawer.classList.remove('hidden'); sheet.classList.add('hidden'); },
  openSheet(){ overlay.classList.remove('hidden'); sheet.classList.remove('hidden'); drawer.classList.add('hidden'); },
  close(){ overlay.classList.add('hidden'); drawer.classList.add('hidden'); sheet.classList.add('hidden'); },
  setAr(on){
    document.documentElement.lang = on ? 'ar' : 'en';
    document.getElementById('app').dir = on ? 'rtl' : 'ltr';
    document.getElementById('pageTitle').textContent = on ? 'التقويم' : 'Calendar';
    document.getElementById('pageSub').textContent = on ? 'عرض يومي وأسبوعي وشهري لجدولك وفريق التوظيف.' : 'Day, week, and month for your schedule and hiring team.';
    document.getElementById('bannerText').textContent = on ? 'معاينة كاناري WATHEFNI — أحداث وهمية للمراجعة فقط · 9' : 'WATHEFNI canary preview — synthetic events for review only · 9';
  },
  mobile(on){ document.body.classList.toggle('mobile', on); }
};
const overlay = document.getElementById('overlay');
const drawer = document.getElementById('drawer');
const sheet = document.getElementById('sheet');
</script>
</body></html>
"""

HTML.write_text(FIXTURE)

CHROMIUM = "/opt/homebrew/bin/chromium"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(HTML.as_uri())

    shots = [
        ("01-desktop-en-week-dense.png", lambda: (page.evaluate("() => { __cal.setAr(false); __cal.mobile(false); __cal.close(); __cal.setView('week') }"))),
        ("02-desktop-en-month.png", lambda: page.evaluate("() => __cal.setView('month')")),
        ("03-desktop-en-day-sparse.png", lambda: page.evaluate("() => __cal.setView('day')")),
        ("04-desktop-en-overlay-drawer.png", lambda: page.evaluate("() => { __cal.setView('week'); __cal.openDrawer() }")),
        ("05-desktop-ar-rtl-week.png", lambda: page.evaluate("() => { __cal.close(); __cal.setAr(true); __cal.setView('week') }")),
        ("06-desktop-ar-rtl-month.png", lambda: page.evaluate("() => __cal.setView('month')")),
        ("07-desktop-ar-rtl-drawer.png", lambda: page.evaluate("() => { __cal.setView('week'); __cal.openDrawer() }")),
    ]
    for name, prep in shots:
        prep()
        page.wait_for_timeout(120)
        page.screenshot(path=str(OUT / name), full_page=True)
        print("wrote", name)

    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.goto(HTML.as_uri())
    mobile.evaluate("() => { __cal.setAr(false); __cal.mobile(true); __cal.setView('day') }")
    mobile.wait_for_timeout(120)
    mobile.screenshot(path=str(OUT / "08-mobile-en-day.png"), full_page=True)
    mobile.evaluate("() => __cal.openSheet()")
    mobile.wait_for_timeout(120)
    mobile.screenshot(path=str(OUT / "09-mobile-en-bottom-sheet.png"), full_page=True)
    mobile.evaluate("() => { __cal.close(); __cal.setAr(true); __cal.setView('day') }")
    mobile.wait_for_timeout(120)
    mobile.screenshot(path=str(OUT / "10-mobile-ar-day.png"), full_page=True)
    print("wrote mobile shots")
    browser.close()

print("SCREENSHOTS_OK", OUT)
