"use client";

import { Plus } from "lucide-react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { DatasetCards } from "@/components/evals/dataset-cards";
import { NewDatasetDialog } from "@/components/evals/dataset-dialogs";
import { NewRunDialog } from "@/components/evals/new-run-dialog";
import { RunsTable } from "@/components/evals/runs-table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useProject } from "@/lib/queries";
import { canEdit } from "@/lib/roles";

function Evaluations() {
  const { project } = useParams<{ project: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const detail = useProject(project);
  const editable = canEdit(detail.data?.role);
  const tab = params.get("tab") === "datasets" ? "datasets" : "runs";
  const [running, setRunning] = useState<{ open: boolean; dataset?: string }>({ open: false });
  const [creating, setCreating] = useState(false);

  return (
    <>
      <PageHeader
        title="Evaluations"
        description="Score pipeline versions on your own questions, compare them, and gate releases on the result."
        actions={
          editable ? (
            <>
              <Button variant="secondary" onClick={() => setCreating(true)}>
                <Plus /> New dataset
              </Button>
              <Button onClick={() => setRunning({ open: true })}>
                <Plus /> New run
              </Button>
            </>
          ) : null
        }
      />
      <Tabs
        value={tab}
        onValueChange={(value) =>
          router.replace(value === "runs" ? pathname : `${pathname}?tab=${value}`, {
            scroll: false,
          })
        }
      >
        <TabsList>
          <TabsTrigger value="runs">Runs</TabsTrigger>
          <TabsTrigger value="datasets">Datasets</TabsTrigger>
        </TabsList>
        <TabsContent value="runs">
          <RunsTable project={project} />
        </TabsContent>
        <TabsContent value="datasets">
          <DatasetCards
            project={project}
            editable={editable}
            onRun={(dataset) => setRunning({ open: true, dataset })}
          />
        </TabsContent>
      </Tabs>
      <NewRunDialog
        project={project}
        open={running.open}
        dataset={running.dataset}
        onOpenChange={(open) => setRunning((current) => ({ ...current, open }))}
      />
      <NewDatasetDialog project={project} open={creating} onOpenChange={setCreating} />
    </>
  );
}

export default function EvaluationsPage() {
  return (
    <PageBody>
      <Suspense fallback={<Skeleton className="h-96" />}>
        <Evaluations />
      </Suspense>
    </PageBody>
  );
}
