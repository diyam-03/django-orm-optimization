/* Query Lab frontend. Plain JavaScript, no build step.
   Set window.QUERYLAB_API = "http://localhost:8000" before this script if the
   frontend is served from a different origin (CORS is already enabled). */
(() => {
  const API = (window.QUERYLAB_API || "") + "/api";
  const $ = (s, el = document) => el.querySelector(s);
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const LINES_PER_SECOND = 240; // the tape prints at the same speed in both lanes

  const lanes = {
    slow: { el: $("#laneSlow"), url: "countries/slow/" },
    fast: { el: $("#laneFast"), url: "countries/fast/" },
  };
  let runId = 0;

  async function api(path, options) {
    const res = await fetch(`${API}/${path}`, options);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }
  const fmt = (n) => Number(n).toLocaleString("en-IN");
  const ms = (n) => (n >= 100 ? Math.round(n) : n >= 10 ? n.toFixed(1) : n.toFixed(2));
  const bytes = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  // ---------------------------------------------------------------- header
  async function loadStats() {
    const chips = $("#chips");
    try {
      const s = await api("stats/");
      chips.replaceChildren(
        el("span", "chip", `${fmt(s.countries)} countries`),
        el("span", "chip", `${s.regions.length} regions`),
        el("span", "chip", `${s.languages} languages, ${s.currencies} currencies`),
        el("span", "chip", s.database === "postgresql" ? "PostgreSQL" : s.database),
      );
      if (!s.demo_tools) {
        $("#index .controls").hidden = true;
        $("#idxOut").replaceChildren(el("p", "warn", "The index benchmark is switched off on this server because it changes data. Run it locally with: python manage.py benchmark"));
      }
      if (s.synthetic) chips.append(el("span", "chip", `${fmt(s.synthetic)} test rows`));
      return s;
    } catch (e) {
      chips.replaceChildren(el("span", "chip", "API not reachable"));
      throw e;
    }
  }

  // ------------------------------------------------------------- the race
  function resetLane(lane) {
    lane.el.classList.remove("done");
    lane.el.querySelectorAll("[data-m]").forEach((n) => (n.textContent = "0"));
    lane.el.querySelector("[data-tape]").replaceChildren();
  }
  const setM = (lane, k, v) => (lane.el.querySelector(`[data-m=${k}]`).textContent = v);

  function showError(lane, message, hint) {
    const li = el("li", "empty");
    li.append(el("strong", null, message), document.createElement("br"), document.createTextNode(hint));
    lane.el.querySelector("[data-tape]").replaceChildren(li);
  }

  function makeLine(q, i) {
    const li = el("li", q.table);
    li.append(el("i"), el("span", "n", String(i + 1)), el("span", "ms", q.ms.toFixed(1)), el("span", "sql", q.sql));
    li.title = q.sql;
    return li;
  }

  // Print the lines of every lane at the same speed. The fast lane finishes almost
  // instantly; the slow lane keeps printing. That contrast is the whole demo.
  function animate(data, myRun) {
    return new Promise((resolve) => {
      const state = Object.entries(data).map(([name, d]) => ({ name, d, shown: 0, db: 0, ol: lanes[name].el.querySelector("[data-tape]"), wrap: lanes[name].el.querySelector(".tape") }));
      const start = performance.now();
      const finish = (s) => {
        const L = lanes[s.name], m = s.d.meta;
        setM(L, "count", fmt(m.query_count)); setM(L, "db", ms(m.db_ms)); setM(L, "total", ms(m.total_ms));
        if (m.tape_truncated) s.ol.append(el("li", "more", `Tape shows the first ${fmt(m.queries.length)} of ${fmt(m.query_count)} queries.`));
        L.el.classList.add("done");
      };
      const step = (now) => {
        if (myRun !== runId) return resolve();
        let pending = false;
        for (const s of state) {
          const q = s.d.meta.queries;
          const target = reduceMotion ? q.length : Math.min(q.length, Math.floor(((now - start) / 1000) * LINES_PER_SECOND));
          if (target > s.shown) {
            const frag = document.createDocumentFragment();
            for (let i = s.shown; i < target; i++) { frag.append(makeLine(q[i], i)); s.db += q[i].ms; }
            s.ol.append(frag);
            s.shown = target;
            s.wrap.scrollTop = s.wrap.scrollHeight;
            setM(lanes[s.name], "count", fmt(s.shown));
            setM(lanes[s.name], "db", ms(s.db));
          }
          if (s.shown < q.length) pending = true;
          else if (!lanes[s.name].el.classList.contains("done")) finish(s);
        }
        pending ? requestAnimationFrame(step) : resolve();
      };
      requestAnimationFrame(step);
    });
  }

  function renderAnatomy(meta, limit) {
    const counts = {};
    meta.queries.forEach((q) => (counts[q.table] = (counts[q.table] || 0) + 1));
    const names = { countries: "country list", region: "region lookups", languages: "language lookups", currencies: "currency lookups" };
    const stack = $("#stack"), legend = $("#legend");
    stack.replaceChildren(); legend.replaceChildren();
    Object.keys(names).forEach((t) => {
      if (!counts[t]) return;
      const seg = el("span"); seg.style.cssText = `width:${(counts[t] / meta.queries.length) * 100}%;--tc:var(--t-${t})`; seg.title = `${names[t]}: ${counts[t]}`;
      stack.append(seg);
      const li = el("li"); li.style.setProperty("--tc", `var(--t-${t})`);
      li.append(el("i"), el("b", null, fmt(counts[t])), document.createTextNode(` ${names[t]}`));
      legend.append(li);
    });
    $("#anatomyNote").textContent = `${limit} countries means 1 query for the list plus 3 for every country: ${limit} + ${limit} + ${limit} lookups. The count grows with the page size, which is why this pattern is called N+1.`;
    $("#anatomy").hidden = false;
  }

  function renderFastSql(meta) {
    const why = {
      join: "One query returns countries and their regions together (JOIN)",
      main: "One query returns the countries",
      prefetch: "One query returns the matching rows for every country on the page (IN list)",
    };
    const ol = $("#fastSql");
    ol.replaceChildren(...meta.queries.map((q) => {
      const li = el("li", q.table);
      li.append(el("span", "why", why[q.kind] || q.table), el("span", "sql", q.sql));
      return li;
    }));
  }

  function setHeadline(slow, fast, limit) {
    $("#headline").textContent = `The same ${limit} countries cost ${fmt(slow)} queries one way and ${fmt(fast)} the other.`;
  }

  async function runRace() {
    const myRun = ++runId;
    const limit = Number($("#limit").value);
    const btn = $("#runBtn");
    btn.disabled = true;
    Object.values(lanes).forEach(resetLane);
    try {
      // One after the other, so the two requests do not compete for the database.
      const slow = await api(`countries/slow/?limit=${limit}`);
      const fast = await api(`countries/fast/?limit=${limit}`);
      if (myRun !== runId) return;
      if (!slow.meta.count) throw Object.assign(new Error("empty"), { empty: true });
      setHeadline(slow.meta.query_count, fast.meta.query_count, slow.meta.returned);
      renderFastSql(fast.meta);
      await animate({ slow, fast }, myRun);
      if (myRun === runId) renderAnatomy(slow.meta, slow.meta.returned);
    } catch (e) {
      const [msg, hint] = e.empty
        ? ["No countries in the database yet.", "Run: python manage.py load_countries"]
        : ["Could not reach the API.", "Start the server with: python manage.py runserver"];
      Object.values(lanes).forEach((l) => showError(l, msg, hint));
    } finally {
      if (myRun === runId) btn.disabled = false;
    }
  }

  // -------------------------------------------------------------- indexes
  function renderIndexes(r) {
    const out = $("#idxOut");
    out.replaceChildren();
    if (!r.supported) { out.append(el("p", "warn", r.reason)); return; }
    if (r.small_table) {
      out.append(el("p", "warn", `Only ${fmt(r.rows)} rows right now. On a table this small PostgreSQL can read everything faster than it can use an index, so the difference is hard to see. Press "Add 200,000 test rows" and run the benchmark again.`));
    }
    const tests = el("div", "tests");
    r.tests.forEach((t) => {
      const box = el("div", "test");
      const pct = Math.max((t.after.ms / Math.max(t.before.ms, 0.001)) * 100, 0.7);
      box.append(el("h3", null, t.title), el("p", "q", t.sql));
      const bars = el("div", "bars");
      [["Without", "before", t.before, 100], ["With", "after", t.after, pct]].forEach(([label, cls, d, w]) => {
        const track = el("div", "track " + cls), fill = el("span", "fill");
        track.append(fill);
        bars.append(el("span", "lab " + cls, label), track, el("span", "val", `${ms(d.ms)} ms`), el("span", "plan", d.plan));
        requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.width = w + "%")));
      });
      box.append(bars);
      const sp = el("div", "speed", `${fmt(t.speedup)}x faster`);
      sp.append(el("small", null, "median of 5 runs, measured by EXPLAIN ANALYZE"));
      box.append(sp);
      tests.append(box);
    });
    out.append(tests);

    const c = r.cost, total = c.table_bytes + c.index_total_bytes;
    const cost = el("div", "cost");
    const disk = el("div"); disk.append(el("h3", null, "Cost 1: disk space"));
    const duo = el("div", "duo"); const a = el("span", "a"), b = el("span", "b");
    a.style.width = (c.table_bytes / total) * 100 + "%"; b.style.width = (c.index_total_bytes / total) * 100 + "%"; duo.append(a, b);
    const leg = el("div", "duo-legend"); leg.append(el("span", null, `Table data ${bytes(c.table_bytes)}`), el("span", null, `Three indexes ${bytes(c.index_total_bytes)}`));
    disk.append(duo, leg, el("p", null, c.indexes.map((i) => `${i.name}: ${bytes(i.bytes)}`).join(". ") + "."));

    const writes = el("div"); writes.append(el("h3", null, `Cost 2: slower writes (${fmt(c.insert_rows)} inserts)`));
    const wb = el("div", "bars"); const maxW = Math.max(c.insert_with_ms, c.insert_without_ms);
    [["Without", "before", c.insert_without_ms], ["With", "after", c.insert_with_ms]].forEach(([label, cls, v]) => {
      const track = el("div", "track " + cls), fill = el("span", "fill"); track.append(fill);
      wb.append(el("span", "lab", label), track, el("span", "val", `${ms(v)} ms`));
      requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.width = (v / maxW) * 100 + "%")));
    });
    writes.append(wb, el("p", null, `Every insert also has to update each index. Here that is ${c.insert_slowdown_pct}% more time. The cca3 unique constraint keeps its own index in both runs.`));
    cost.append(disk, writes);
    out.append(cost);

    const best = Math.max(...r.tests.map((t) => t.speedup)), worst = Math.min(...r.tests.map((t) => t.speedup));
    out.append(el("p", "verdict", `Reads got ${fmt(worst)}x to ${fmt(best)}x faster. The price: ${bytes(c.index_total_bytes)} of extra disk and ${c.insert_slowdown_pct}% slower inserts. Worth it for columns you filter or sort by often, wasteful on columns you never query.`));
  }

  async function runIndexBench() {
    const btns = ["#idxBtn", "#inflateBtn", "#resetBtn"].map((s) => $(s)); const status = $("#idxStatus");
    btns.forEach((b) => (b.disabled = true));
    status.textContent = "Measuring. Each query runs 6 times with and without indexes, this takes a few seconds.";
    try { renderIndexes(await api("benchmark/indexes/")); status.textContent = ""; }
    catch (e) { status.textContent = "Benchmark failed. Check the server log."; }
    finally { btns.forEach((b) => (b.disabled = false)); }
  }

  async function dataset(action, label) {
    const btns = ["#idxBtn", "#inflateBtn", "#resetBtn"].map((s) => $(s)); const status = $("#idxStatus");
    btns.forEach((b) => (b.disabled = true)); status.textContent = label;
    try {
      await api("dataset/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, rows: 200000 }) });
      status.textContent = action === "inflate" ? "Added 200,000 test rows. Run the benchmark." : "Test rows removed.";
      await loadStats();
    } catch (e) { status.textContent = "Request failed. Check the server log."; }
    finally { btns.forEach((b) => (b.disabled = false)); }
  }

  // ------------------------------------------------------------------ wiring
  const limit = $("#limit"); let timer;
  limit.addEventListener("input", () => { $("#limitOut").textContent = limit.value; clearTimeout(timer); timer = setTimeout(runRace, 450); });
  $("#runBtn").addEventListener("click", runRace);
  $("#idxBtn").addEventListener("click", runIndexBench);
  $("#inflateBtn").addEventListener("click", () => dataset("inflate", "Adding 200,000 rows. This takes about 10 seconds."));
  $("#resetBtn").addEventListener("click", () => dataset("reset", "Removing test rows."));

  // highlight the current section in the left rail
  const links = [...document.querySelectorAll(".rail a")];
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id));
  }), { rootMargin: "-30% 0px -60% 0px" });
  document.querySelectorAll("main section").forEach((s) => io.observe(s));

  loadStats().then((s) => { if (s.max_limit) limit.max = s.max_limit; runRace(); }).catch(() => runRace());
})();
