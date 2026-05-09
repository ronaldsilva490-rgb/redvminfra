// STADIA — ProductVisual: Unsplash photography per category
// Each product picks a curated photo by category + team accent overlay

const STADIA_UNSPLASH = {
  camisas: [
    "photo-1517466787929-bc90951d0974", // jersey
    "photo-1556906781-9a412961c28c", // football kit
    "photo-1577471488278-16eec37ffcc2", // jersey on hanger
    "photo-1542652694-40abf526446e", // soccer jersey
    "photo-1606107557195-0e29a4b5b4aa", // sport tee
  ],
  chuteiras: [
    "photo-1511886929837-354d827aae26", // football boots
    "photo-1542291026-7eec264c27ff", // red sneakers
    "photo-1606890737304-57a1ca8a5b62", // boots
    "photo-1539185441755-769473a23570", // shoes
    "photo-1608231387042-66d1773070a5", // cleats
  ],
  bolas: [
    "photo-1614632537190-23e4146777db", // football
    "photo-1551958219-acbc608c6377", // ball on field
    "photo-1574629810360-7efbbe195018", // soccer ball
    "photo-1486286701208-1d58e9338013", // ball
    "photo-1518604666860-9ed391f76460", // ball net
  ],
  treino: [
    "photo-1517836357463-d25dfeac3438", // gym shorts
    "photo-1532667449560-72a95c8d381b", // training gear
    "photo-1581009146145-b5ef050c2e1e", // workout clothes
    "photo-1599058917765-a780eda07a3e", // gym
    "photo-1571019613454-1cb2f99b2d8b", // training
  ],
  acessorios: [
    "photo-1588850561407-ed78c282e89b", // cap
    "photo-1521369909029-2afed882baee", // socks
    "photo-1620231150904-2cdcc6b3933c", // headband
    "photo-1556306535-0f09a537f0a3", // cap
    "photo-1622445275576-721325763afe", // gloves
  ],
  femme: [
    "photo-1518310383802-640c2de311b2", // sports bra
    "photo-1571019613540-996a69725ef4", // women fitness
    "photo-1518310952931-b1de897abd40", // women sport
    "photo-1594381898411-846e7d193883", // training top
    "photo-1583500178690-f7fd39b51242", // legging
  ],
};

function ProductVisual({ p }) {
  const list = STADIA_UNSPLASH[p.category] || STADIA_UNSPLASH.camisas;
  const idx = Math.abs(parseInt(p.id.replace(/\D/g, ""), 10) || 0) % list.length;
  const photoId = list[idx];
  const url = `https://images.unsplash.com/${photoId}?w=720&q=75&auto=format&fit=crop`;
  const accent = p.colors?.[1]?.hex || p.colors?.[0]?.hex || "#c8ff00";

  return (
    <React.Fragment>
      <img
        src={url}
        alt={p.name}
        loading="lazy"
        style={{
          position: "absolute", inset: 0,
          width: "100%", height: "100%",
          objectFit: "cover",
          display: "block",
        }}
        onError={(e) => { e.currentTarget.style.display = "none"; }}
      />
      <span
        style={{
          position: "absolute", inset: 0,
          background: `linear-gradient(160deg, ${accent}22 0%, transparent 40%, rgba(0,0,0,0.25) 100%)`,
          pointerEvents: "none",
        }}
      />
    </React.Fragment>
  );
}

window.STADIA_PRODUCT_VISUAL = ProductVisual;
