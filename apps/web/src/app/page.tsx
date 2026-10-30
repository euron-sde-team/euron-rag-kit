"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui/feedback";
import { ApiError } from "@/lib/api";
import { pickProject } from "@/lib/project-choice";
import { useMe } from "@/lib/queries";
import { LAST_PROJECT_KEY, readLocal } from "@/lib/storage";

export default function Home() {
  const router = useRouter();
  const me = useMe();

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) {
      router.replace("/login");
      return;
    }
    if (!me.data) return;
    const target = pickProject(me.data.projects, readLocal(LAST_PROJECT_KEY));
    router.replace(target ? `/p/${target}` : "/welcome");
  }, [me.data, me.error, router]);

  return (
    <main className="flex min-h-dvh items-center justify-center">
      <Spinner className="size-5" />
    </main>
  );
}
