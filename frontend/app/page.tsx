import { AuthGate } from "@/components/AuthGate";
import { Chat } from "@/components/Chat";

export default function Home() {
  return (
    <AuthGate>
      <Chat />
    </AuthGate>
  );
}
