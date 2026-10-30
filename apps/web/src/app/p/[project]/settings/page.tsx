"use client";

import { useParams } from "next/navigation";

import { ActivityPanel } from "@/components/settings/activity-panel";
import { ApiKeysPanel } from "@/components/settings/api-keys-panel";
import { GeneralPanel } from "@/components/settings/general-panel";
import { MembersPanel } from "@/components/settings/members-panel";
import { ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useProject } from "@/lib/queries";
import { isOwner } from "@/lib/roles";

export default function SettingsPage() {
  const { project } = useParams<{ project: string }>();
  const query = useProject(project);
  const data = query.data;
  const owner = isOwner(data?.role);

  return (
    <PageBody className="max-w-4xl">
      <PageHeader title="Settings" description="Project details, people and programmatic access." />
      {query.error ? <ErrorNotice message={query.error.message} /> : null}
      {!data ? (
        <Skeleton className="h-64" />
      ) : (
        <Tabs defaultValue="general">
          <TabsList>
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="members">Members</TabsTrigger>
            {owner ? <TabsTrigger value="api-keys">API keys</TabsTrigger> : null}
            <TabsTrigger value="activity">Activity</TabsTrigger>
          </TabsList>
          <TabsContent value="general">
            <GeneralPanel
              key={`${data.name}-${data.description}`}
              project={data}
              editable={owner}
            />
          </TabsContent>
          <TabsContent value="members">
            <MembersPanel project={data.slug} isOwner={owner} />
          </TabsContent>
          {owner ? (
            <TabsContent value="api-keys">
              <ApiKeysPanel project={data.slug} />
            </TabsContent>
          ) : null}
          <TabsContent value="activity">
            <ActivityPanel project={data.slug} />
          </TabsContent>
        </Tabs>
      )}
    </PageBody>
  );
}
