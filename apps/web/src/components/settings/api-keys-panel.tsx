"use client";

import { KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CodeBlock, CopyField } from "@/components/copy-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { FieldHint, Input, Label, NativeSelect } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate, formatRelative } from "@/lib/format";
import { useApiKeyActions, useApiKeys, useCollections, useDatasets } from "@/lib/queries";
import { runtimeEnv } from "@/lib/runtime-env";
import { snippets } from "@/lib/snippets";
import type { ApiKeyCreated } from "@/lib/types";

function Examples({ project, keyText }: { project: string; keyText: string }) {
  const collections = useCollections(project);
  const datasets = useDatasets(project);
  const examples = snippets({
    apiUrl: runtimeEnv().apiUrl,
    project,
    collection: collections.data?.[0]?.slug ?? "my-collection",
    dataset: datasets.data?.[0]?.slug ?? "my-dataset",
    key: keyText,
  });
  return (
    <Tabs defaultValue="python">
      <TabsList>
        <TabsTrigger value="python">Python SDK</TabsTrigger>
        <TabsTrigger value="curl">curl</TabsTrigger>
        <TabsTrigger value="cli">CLI and CI</TabsTrigger>
      </TabsList>
      <TabsContent value="python" className="pt-3">
        <CodeBlock code={examples.python} label="Python example" />
        <FieldHint className="mt-2">
          Install with <code className="font-mono">pip install ./sdk/python</code> from the
          repository.
        </FieldHint>
      </TabsContent>
      <TabsContent value="curl" className="pt-3">
        <CodeBlock code={examples.curl} label="curl example" />
      </TabsContent>
      <TabsContent value="cli" className="pt-3">
        <CodeBlock code={examples.cli} label="CLI example" />
        <FieldHint className="mt-2">
          The gate exits 1 when a metric falls below its floor or drops against the baseline, so CI
          fails the pull request.
        </FieldHint>
      </TabsContent>
    </Tabs>
  );
}

export function ApiKeysPanel({ project }: { project: string }) {
  const keys = useApiKeys(project);
  const actions = useApiKeyActions(project);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState<"viewer" | "editor">("viewer");
  const [expires, setExpires] = useState("90");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      const key = await actions.create.mutateAsync({
        name,
        role,
        expires_in_days: expires ? Number(expires) : null,
      });
      setCreated(key);
      setName("");
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="border-border flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3.5">
          <p className="text-muted-foreground text-[13px]">
            Keys let services, notebooks and CI call this project. Viewers query and answer; editors
            can also ingest and run evaluations.
          </p>
          <Button size="sm" onClick={() => setOpen(true)}>
            <KeyRound /> Create key
          </Button>
        </div>
        {keys.isLoading ? (
          <div className="p-5">
            <Skeleton className="h-10" />
          </div>
        ) : keys.data?.length ? (
          <ul className="divide-border divide-y">
            {keys.data.map((key) => (
              <li key={key.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-[13.5px] font-medium">
                    {key.name}
                    <Badge tone="outline" className="capitalize">
                      {key.role}
                    </Badge>
                    {key.revoked_at ? <Badge tone="danger">Revoked</Badge> : null}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    <code className="font-mono">rgk_{key.prefix}_...</code>, created{" "}
                    {formatRelative(key.created_at)},{" "}
                    {key.last_used_at
                      ? `last used ${formatRelative(key.last_used_at)}`
                      : "never used"}
                    {key.expires_at ? `, expires ${formatDate(key.expires_at)}` : ""}
                  </p>
                </div>
                {!key.revoked_at ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      try {
                        await actions.revoke.mutateAsync(key.id);
                        toast.success(`${key.name} revoked`);
                      } catch (error) {
                        toast.error((error as Error).message);
                      }
                    }}
                  >
                    Revoke
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<KeyRound />}
            title="No API keys yet"
            description="Create one to call RAGKit from the SDK, scripts and CI."
          />
        )}
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Use a key</CardTitle>
            <CardDescription>The same calls the dashboard makes, from your code.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <Examples project={project} keyText="rgk_..." />
        </CardContent>
      </Card>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setCreated(null);
        }}
      >
        <DialogContent
          title={created ? "Copy your key now" : "Create an API key"}
          description={
            created
              ? "This is the only time the full key is shown. Only a keyed hash is stored."
              : "Keys are scoped to this project."
          }
          className="w-[min(94vw,40rem)]"
        >
          {created ? (
            <div className="space-y-4">
              <CopyField value={created.key} label="API key" />
              <Examples project={project} keyText={created.key} />
              <DialogFooter>
                <Button
                  onClick={() => {
                    setOpen(false);
                    setCreated(null);
                  }}
                >
                  Done
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={create} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="key-name">Name</Label>
                <Input
                  id="key-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Docs assistant (production)"
                  required
                  autoFocus
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="key-role">Access</Label>
                  <NativeSelect
                    id="key-role"
                    value={role}
                    onChange={(e) => setRole(e.target.value as "viewer" | "editor")}
                  >
                    <option value="viewer">Viewer: query and answer</option>
                    <option value="editor">Editor: also ingest and evaluate</option>
                  </NativeSelect>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="key-expiry">Expires</Label>
                  <NativeSelect
                    id="key-expiry"
                    value={expires}
                    onChange={(e) => setExpires(e.target.value)}
                  >
                    <option value="30">In 30 days</option>
                    <option value="90">In 90 days</option>
                    <option value="365">In a year</option>
                    <option value="">Never</option>
                  </NativeSelect>
                </div>
              </div>
              <FieldHint>
                Send it as <code className="font-mono">Authorization: Bearer rgk_...</code>
              </FieldHint>
              {actions.create.error ? <ErrorNotice message={actions.create.error.message} /> : null}
              <DialogFooter>
                <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!name.trim() || actions.create.isPending}>
                  Create key
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
