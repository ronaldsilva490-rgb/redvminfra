// STADIA — icons (original geometric line art, no brand marks)

const Icon = ({ name, size = 18, stroke = 1.6, ...rest }) => {
  const props = {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: stroke,
    strokeLinecap: "round", strokeLinejoin: "round",
    ...rest,
  };
  switch (name) {
    case "search": return (
      <svg {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    );
    case "user": return (
      <svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/></svg>
    );
    case "bag": return (
      <svg {...props}><path d="M5 8h14l-1 12H6L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/></svg>
    );
    case "heart": return (
      <svg {...props}><path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10Z"/></svg>
    );
    case "menu": return (
      <svg {...props}><path d="M3 6h18M3 12h18M3 18h18"/></svg>
    );
    case "x": return (
      <svg {...props}><path d="M6 6l12 12M18 6 6 18"/></svg>
    );
    case "arrow-right": return (
      <svg {...props}><path d="M5 12h14M13 6l6 6-6 6"/></svg>
    );
    case "arrow-left": return (
      <svg {...props}><path d="M19 12H5M11 6l-6 6 6 6"/></svg>
    );
    case "arrow-up-right": return (
      <svg {...props}><path d="M7 17 17 7M9 7h8v8"/></svg>
    );
    case "chevron-down": return (
      <svg {...props}><path d="m6 9 6 6 6-6"/></svg>
    );
    case "chevron-right": return (
      <svg {...props}><path d="m9 6 6 6-6 6"/></svg>
    );
    case "check": return (
      <svg {...props}><path d="m4 12 5 5L20 6"/></svg>
    );
    case "plus": return (
      <svg {...props}><path d="M12 5v14M5 12h14"/></svg>
    );
    case "minus": return (
      <svg {...props}><path d="M5 12h14"/></svg>
    );
    case "trash": return (
      <svg {...props}><path d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/></svg>
    );
    case "eye": return (
      <svg {...props}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>
    );
    case "eye-off": return (
      <svg {...props}><path d="M3 3l18 18"/><path d="M10.6 6.1A10 10 0 0 1 12 6c6 0 10 6 10 6a14 14 0 0 1-3.2 3.5"/><path d="M6.6 6.6A14 14 0 0 0 2 12s4 6 10 6c1.6 0 3-.3 4.4-.9"/></svg>
    );
    case "filter": return (
      <svg {...props}><path d="M3 5h18l-7 9v6l-4-2v-4L3 5Z"/></svg>
    );
    case "grid": return (
      <svg {...props}><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
    );
    case "rows": return (
      <svg {...props}><rect x="3" y="4" width="18" height="6"/><rect x="3" y="14" width="18" height="6"/></svg>
    );
    case "shirt": return (
      <svg {...props}><path d="M4 6 8 4l4 3 4-3 4 2-2 4-2-1v11H6V9L4 10 4 6Z"/></svg>
    );
    case "boot": return (
      <svg {...props}><path d="M5 4h6v9l9 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M11 13h9"/></svg>
    );
    case "ball": return (
      <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18M5 6c5 1 9 4 14 8M19 6c-5 1-9 4-14 8"/></svg>
    );
    case "dumbbell": return (
      <svg {...props}><rect x="2" y="9" width="3" height="6" rx="1"/><rect x="19" y="9" width="3" height="6" rx="1"/><path d="M5 12h2v-3h2v6H7v-3M19 12h-2v-3h-2v6h2v-3"/><path d="M9 12h6"/></svg>
    );
    case "tag": return (
      <svg {...props}><path d="m3 12 9-9h7v7l-9 9Z"/><circle cx="15" cy="9" r="1.5"/></svg>
    );
    case "spark": return (
      <svg {...props}><path d="M12 3v6M12 15v6M3 12h6M15 12h6M5 5l4 4M15 15l4 4M19 5l-4 4M9 15l-4 4"/></svg>
    );
    case "truck": return (
      <svg {...props}><rect x="2" y="6" width="13" height="10"/><path d="M15 9h4l3 3v4h-7"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></svg>
    );
    case "shield": return (
      <svg {...props}><path d="M12 3 5 6v6c0 4.5 3 8 7 9 4-1 7-4.5 7-9V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></svg>
    );
    case "spark-2": return (
      <svg {...props}><path d="M12 3v18M3 12h18"/><circle cx="12" cy="12" r="3"/></svg>
    );
    case "lightning": return (
      <svg {...props}><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/></svg>
    );
    case "star": return (
      <svg {...props}><path d="m12 3 2.6 5.6 6.1.6-4.6 4.2 1.3 6L12 16.5 6.6 19.4l1.3-6L3.3 9.2l6.1-.6L12 3Z" fill="currentColor"/></svg>
    );
    case "star-o": return (
      <svg {...props}><path d="m12 3 2.6 5.6 6.1.6-4.6 4.2 1.3 6L12 16.5 6.6 19.4l1.3-6L3.3 9.2l6.1-.6L12 3Z"/></svg>
    );
    case "lock": return (
      <svg {...props}><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V8a4 4 0 1 1 8 0v3"/></svg>
    );
    case "pin": return (
      <svg {...props}><path d="M12 22s7-7 7-12a7 7 0 1 0-14 0c0 5 7 12 7 12Z"/><circle cx="12" cy="10" r="2.5"/></svg>
    );
    case "card": return (
      <svg {...props}><rect x="2" y="6" width="20" height="14" rx="2"/><path d="M2 10h20M6 16h4"/></svg>
    );
    case "pix": return (
      <svg {...props}><path d="m12 3 9 9-9 9-9-9 9-9Z"/><path d="M7 12h10M12 7v10"/></svg>
    );
    case "boleto": return (
      <svg {...props}><rect x="3" y="5" width="2" height="14"/><rect x="7" y="5" width="1" height="14"/><rect x="10" y="5" width="3" height="14"/><rect x="15" y="5" width="1" height="14"/><rect x="18" y="5" width="3" height="14"/></svg>
    );
    case "sparkles": return (
      <svg {...props}><path d="m12 3 1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7L12 3ZM19 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2ZM5 16l.7 1.7L7.4 18l-1.7.6L5 20l-.6-1.4L2.7 18l1.7-.6L5 16Z" fill="currentColor"/></svg>
    );
    case "info": return (
      <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/></svg>
    );
    case "alert": return (
      <svg {...props}><path d="m12 3 10 18H2L12 3Z"/><path d="M12 10v4M12 17v.01"/></svg>
    );
    case "badge-check": return (
      <svg {...props}><path d="m12 3 2 2 3-1 1 3 3 1-1 3 1 3-3 1-1 3-3-1-2 2-2-2-3 1-1-3-3-1 1-3-1-3 3-1 1-3 3 1 2-2Z"/><path d="m9 12 2 2 4-4"/></svg>
    );
    case "settings": return (
      <svg {...props}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3 1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8 1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>
    );
    case "play": return (
      <svg {...props}><path d="M7 4v16l13-8L7 4Z" fill="currentColor"/></svg>
    );
    case "logout": return (
      <svg {...props}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>
    );
    case "package": return (
      <svg {...props}><path d="m3 8 9-5 9 5-9 5-9-5Z"/><path d="M3 8v8l9 5 9-5V8M12 13v8"/></svg>
    );
    case "headset": return (
      <svg {...props}><path d="M4 14a8 8 0 1 1 16 0v3a3 3 0 0 1-3 3h-1v-7h4M4 14v3a3 3 0 0 0 3 3h1v-7H4Z"/></svg>
    );
    case "store": return (
      <svg {...props}><path d="m3 7 2-3h14l2 3v3a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0V7Z"/><path d="M5 11v9h14v-9"/></svg>
    );
    case "globe": return (
      <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>
    );
    case "compress": return (
      <svg {...props}><path d="M9 3v6H3M21 9h-6V3M3 15h6v6M15 21v-6h6"/></svg>
    );
    default: return null;
  }
};

window.Icon = Icon;
