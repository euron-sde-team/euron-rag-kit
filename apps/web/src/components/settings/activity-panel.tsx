"use client";

import { History } from "lucide-react";

import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { describeEvent } from "@/lib/activity";
import { formatRelative } from "@/lib/format";
import { useActivity } from "@/lib/queries";

export function ActivityPanel({ project }: { project: string }) {
  const activity = useActivity(project);
  if (activity.isLoading) return <Skeleton className="h-40" />;
  const events = activity.data?.items ?? [];
  return (
    <Card>
      {events.length ? (
        <ol className="divide-border divide-y">
          {events.map((event) => {
            const { actor, phrase } = describeEvent(event);
            return (
              <li
                key={event.id}
                className="flex items-start justify-between gap-4 px-5 py-3 text-[13px]"
              >
                <p>
                  <span className="font-medium">{actor}</span>{" "}
                  <span className="text-muted-foreground">{phrase}</span>
                </p>
                <time dateTime={event.created_at} className="text-subtle shrink-0 text-xs">
                  {formatRelative(event.created_at)}
                </time>
              </li>
            );
          })}
        </ol>
      ) : (
        <EmptyState icon={<History />} title="No activity yet" />
      )}
    </Card>
  );
}
