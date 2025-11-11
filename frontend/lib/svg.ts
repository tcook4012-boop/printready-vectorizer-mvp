// frontend/lib/svg.ts

/**
 * Step 1 — fast regex cleanup of namespaces/tiny issues.
 */
function regexScrubNamespaces(s: string): string {
  let t = s.trim();

  // keep only outermost <svg>...</svg>
  const open = t.search(/<\s*([a-zA-Z0-9:_-]+)\b[^>]*>/);
  const close = t.search(/<\/\s*svg\s*>/i);
  if (open === -1 || close === -1) return t; // fall through to XML path
  t = t.slice(open, close + "</svg>".length);

  // tags: <ns0:svg> -> <svg>, </ns0:svg> -> </svg>
  t = t.replace(/<\s*[a-zA-Z_][\w.-]*:\s*svg\b/gi, "<svg");
  t = t.replace(/<\/\s*[a-zA-Z_][\w.-]*:\s*svg\s*>/gi, "</svg>");

  // any other namespaced tags: <nsX:foo ...> -> <foo ...>, </nsX:foo> -> </foo>
  t = t.replace(/<\s*\/\s*([a-zA-Z_][\w.-]*):/g, "</");
  t = t.replace(/<\s*([a-zA-Z_][\w.-]*):/g, "<");

  // attributes: nsX:href="..." -> href="..."
  t = t.replace(/\s([a-zA-Z_][\w.-]*):([a-zA-Z_][\w.-]*)=/g, " $2=");

  // drop xmlns:* attributes; ensure base xmlns
  t = t.replace(/\sxmlns:[a-zA-Z_][\w.-]*="[^"]*"/g, "");
  if (!/\sxmlns\s*=/.test(t)) {
    t = t.replace(/<svg\b/i, '<svg xmlns="http://www.w3.org/2000/svg"');
  }

  // inject viewBox if missing using width/height
  if (!/\sviewBox\s*=\s*"/i.test(t)) {
    const w = t.match(/\swidth\s*=\s*"([\d.]+)"/i);
    const h = t.match(/\sheight\s*=\s*"([\d.]+)"/i);
    if (w && h) {
      t = t.replace(/<svg\b/i, `<svg viewBox="0 0 ${Number(w[1])} ${Number(h[1])}"`);
    } else {
      t = t.replace(/<svg\b/i, `<svg viewBox="0 0 1000 1000"`);
    }
  }

  // remove fixed sizing so CSS can scale
  t = t.replace(/\swidth\s*=\s*"[^"]*"/gi, "");
  t = t.replace(/\sheight\s*=\s*"[^"]*"/gi, "");

  // strip xml header/doctype
  t = t.replace(/<\?xml[^>]*>/gi, "");
  t = t.replace(/<!DOCTYPE[^>]*>/gi, "");

  return t.trim();
}

/**
 * Step 2 — robust XML rebuild with namespaces stripped.
 * If regex left any prefix like "<ns0:svg" or attributes with "ns0:",
 * we parse and reconstruct a clean tree.
 */
function xmlRebuildWithoutNamespaces(raw: string): string {
  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, "image/svg+xml");
  const root = doc.documentElement;
  if (!root || root.nodeName.toLowerCase().includes("parsererror")) return "";

  const SVG_NS = "http://www.w3.org/2000/svg";

  function cloneSansNS(n: Element, parent: Element | null): Element {
    // strip any prefix from tag name
    const localName = n.localName || n.nodeName.replace(/^.*:/, "");
    const el = doc.createElementNS(SVG_NS, localName);

    // copy attributes without prefixes
    for (const attr of Array.from(n.attributes)) {
      const name = (attr.localName || attr.name.replace(/^.*:/, "")).toLowerCase();
      if (name.startsWith("xmlns")) continue; // drop any xmlns / xmlns:*
      el.setAttribute(name, attr.value);
    }

    // recurse children
    for (const child of Array.from(n.childNodes)) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        el.appendChild(cloneSansNS(child as Element, el));
      } else {
        el.appendChild(child.cloneNode(true));
      }
    }
    return el;
  }

  const cleanSvg = cloneSansNS(root, null);

  // ensure base xmlns + viewBox
  cleanSvg.setAttribute("xmlns", SVG_NS);
  if (!cleanSvg.getAttribute("viewBox")) {
    const w = cleanSvg.getAttribute("width");
    const h = cleanSvg.getAttribute("height");
    if (w && h) {
      cleanSvg.setAttribute("viewBox", `0 0 ${Number(w)} ${Number(h)}`);
    } else {
      cleanSvg.setAttribute("viewBox", "0 0 1000 1000");
    }
  }
  // drop fixed sizing so container controls size
  cleanSvg.removeAttribute("width");
  cleanSvg.removeAttribute("height");

  const ser = new XMLSerializer();
  return ser.serializeToString(cleanSvg);
}

/**
 * Public API: normalize raw server response into an embeddable <svg>.
 * 1) fast regex scrub; 2) if still namespaced, XML rebuild.
 */
export function normalizeSvg(raw: string): string {
  if (!raw) return "";
  if (raw.trim().startsWith("{") || raw.trim().startsWith("[")) return ""; // looks like JSON error
  let s = regexScrubNamespaces(raw);

  // If any namespaced tag remains, rebuild via XML
  if (/(^|<)\/?\s*[a-zA-Z_][\w.-]*:/.test(s) || /^<ns\d*:svg/i.test(raw.trim())) {
    const rebuilt = xmlRebuildWithoutNamespaces(raw);
    if (rebuilt) s = rebuilt;
  }

  // final sanity
  return /<svg\b/i.test(s) ? s : "";
}
