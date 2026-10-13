import { useNavigate } from "react-router-dom";
import { useOptionalMarket } from "@/markets/MarketContext";
import { MARKETS, parseMarketId } from "@/markets/registry";
import { useGrantedMarkets } from "@/markets/session";

/** US Equities / 中国 A股. Switching goes to the other market's home; nothing carries over. */
export default function MarketSelector() {
  const market = useOptionalMarket();
  const grants = useGrantedMarkets();
  const navigate = useNavigate();
  return (
    <label className="flex items-center gap-2 text-xs text-neutral-400">
      Market
      <select
        aria-label="Market"
        value={market?.id ?? ""}
        onChange={(e) => {
          const id = parseMarketId(e.target.value);
          if (id) navigate(MARKETS[id].basePath);
        }}
        className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-200"
      >
        {market === null && (
          <option value="" disabled>
            Choose a market
          </option>
        )}
        {grants.map((id) => (
          <option key={id} value={id}>
            {MARKETS[id].label}
          </option>
        ))}
      </select>
    </label>
  );
}
