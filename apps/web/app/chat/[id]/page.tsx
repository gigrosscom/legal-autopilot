"use client";

import { use } from "react";
import { Chat } from "@/components/Chat";

export default function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <Chat caseId={id} />;
}
