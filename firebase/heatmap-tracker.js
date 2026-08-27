/*
Click/scroll tracker for the peasyanglais.fr heatmap feature.
Install: paste this whole block (with <script type="module"> tags) into a
WPCode "Insert Headers and Footers" snippet set to load site-wide in the
footer. It writes one Firestore document per pageview (batched client-side,
flushed on tab-hide/unload) - no per-click network requests.

No PII collected: only click position as % of page size, page path, a
random per-tab session id, and max scroll depth.
*/

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.18.0/firebase-app.js";
import { getFirestore, collection, addDoc, serverTimestamp } from "https://www.gstatic.com/firebasejs/12.18.0/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyAf6g0_HeNZOL3H7LY6OR4t1vVjCkXPpPY",
  authDomain: "peasy-mapa-de-calor.firebaseapp.com",
  projectId: "peasy-mapa-de-calor",
  storageBucket: "peasy-mapa-de-calor.firebasestorage.app",
  messagingSenderId: "304565910253",
  appId: "1:304565910253:web:aa9f3e433f803650a86ae4"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

(function () {
  function deviceBucket(width) {
    if (width < 600) return "mobile";
    if (width < 1025) return "tablet";
    return "desktop";
  }

  function pageHeight() {
    return Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, window.innerHeight);
  }
  function pageWidth() {
    return Math.max(document.documentElement.scrollWidth, document.body.scrollWidth, window.innerWidth);
  }

  const SESSION_KEY = "peasy_hm_session";
  let sessionId = sessionStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    sessionStorage.setItem(SESSION_KEY, sessionId);
  }

  const clicks = [];
  let maxScroll = 0;

  document.addEventListener(
    "click",
    (ev) => {
      if (clicks.length >= 200) return;
      const ph = pageHeight();
      const pw = pageWidth();
      if (!ph || !pw) return;
      clicks.push({
        x_pct: Math.round((ev.pageX / pw) * 1000) / 10,
        y_pct: Math.round((ev.pageY / ph) * 1000) / 10,
      });
    },
    { capture: true, passive: true }
  );

  function updateScroll() {
    const ph = pageHeight();
    if (!ph) return;
    const scrolled = window.scrollY + window.innerHeight;
    const pct = Math.min(100, Math.round((scrolled / ph) * 100));
    if (pct > maxScroll) maxScroll = pct;
  }
  window.addEventListener("scroll", updateScroll, { passive: true });
  updateScroll();

  function flush() {
    if (clicks.length === 0 && maxScroll === 0) return;
    const payload = {
      path: location.pathname,
      device: deviceBucket(window.innerWidth),
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      page_width: pageWidth(),
      page_height: pageHeight(),
      clicks: clicks.slice(),
      max_scroll_pct: maxScroll,
      session_id: sessionId,
      created_at: serverTimestamp(),
    };
    clicks.length = 0;
    addDoc(collection(db, "pageviews"), payload).catch(() => {});
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);
})();
