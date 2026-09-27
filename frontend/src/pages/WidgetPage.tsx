import { useSearchParams } from "react-router";
import ChatWidget from "../../widget/ChatWidget";

export default function WidgetPage() {
  const [params] = useSearchParams();
  const channel = params.get("channel");
  const token = params.get("token");
  if (!channel || !token) {
    return <p className="p-4 text-sm text-slate-600">This chat link is incomplete.</p>;
  }
  return <ChatWidget channelId={channel} token={token} />;
}
