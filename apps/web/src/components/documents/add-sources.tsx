"use client";

import { FileUp, X } from "lucide-react";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { FieldHint, Input, Label, NativeSelect, Textarea } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import { useIngest, useSystemInfo } from "@/lib/queries";
import type { IngestResult } from "@/lib/types";

/** Parse the optional metadata box: empty is fine, anything else must be a JSON object. */
function parseMetadata(text: string): Record<string, unknown> | string {
  if (!text.trim()) return {};
  try {
    const value: unknown = JSON.parse(text);
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  } catch {
    // Reported below.
  }
  return 'Metadata must be a JSON object, for example {"section": "guides"}.';
}

function summarize(result: IngestResult): string {
  const parts = [`${result.created.length} added`];
  if (result.duplicates.length) parts.push(`${result.duplicates.length} already present`);
  if (result.rejected.length) parts.push(`${result.rejected.length} rejected`);
  return parts.join(", ");
}

function MetadataField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>Metadata</Label>
      <Textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder='{"section": "guides", "audience": "developers"}'
        className="min-h-16 font-mono text-[12.5px]"
      />
      <FieldHint>Optional JSON, copied onto every chunk so queries can filter on it.</FieldHint>
    </div>
  );
}

export function AddSourcesDialog({
  project,
  collection,
  open,
  onOpenChange,
}: {
  project: string;
  collection: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const system = useSystemInfo();
  const ingest = useIngest(project, collection);
  const input = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState("files");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [metadata, setMetadata] = useState("");
  const [title, setTitle] = useState("");
  const [format, setFormat] = useState<"markdown" | "text">("markdown");
  const [text, setText] = useState("");
  const [urls, setUrls] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [rejected, setRejected] = useState<IngestResult["rejected"]>([]);
  const pending = ingest.upload.isPending || ingest.importSources.isPending;
  const accept = system.data?.accepted_extensions.join(",");

  function reset() {
    setFiles([]);
    setMetadata("");
    setTitle("");
    setText("");
    setUrls("");
    setProblem(null);
    setRejected([]);
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    setFiles((current) => [...current, ...Array.from(list)].slice(0, 20));
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  function finish(result: IngestResult) {
    toast.success(summarize(result));
    if (result.rejected.length) {
      setRejected(result.rejected);
      return;
    }
    reset();
    onOpenChange(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setRejected([]);
    const meta = parseMetadata(metadata);
    if (typeof meta === "string") {
      setProblem(meta);
      return;
    }
    try {
      if (tab === "files") {
        finish(await ingest.upload.mutateAsync({ files, metadata: meta }));
      } else if (tab === "text") {
        finish(
          await ingest.importSources.mutateAsync([
            { type: "text", title, text, format, metadata: meta },
          ]),
        );
      } else {
        const lines = urls
          .split(/\s+/)
          .map((line) => line.trim())
          .filter(Boolean);
        finish(
          await ingest.importSources.mutateAsync(
            lines.map((url) => ({ type: "url", url, metadata: meta })),
          ),
        );
      }
    } catch (error) {
      setProblem((error as Error).message);
    }
  }

  const ready =
    tab === "files"
      ? files.length > 0
      : tab === "text"
        ? Boolean(title.trim() && text.trim())
        : Boolean(urls.trim());

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent
        title="Add sources"
        description="Documents are parsed once, then chunked and embedded by every pipeline version's index."
        className="w-[min(94vw,38rem)]"
      >
        <form onSubmit={submit} className="space-y-4">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="files">Files</TabsTrigger>
              <TabsTrigger value="text">Text</TabsTrigger>
              <TabsTrigger value="urls">Web pages</TabsTrigger>
            </TabsList>
            <TabsContent value="files" className="space-y-3">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={cn(
                  "border-input flex flex-col items-center justify-center rounded-xl border border-dashed px-4 py-7 text-center transition-colors",
                  dragging && "border-primary bg-accent/50",
                )}
              >
                <FileUp className="text-primary mb-2 size-6" aria-hidden />
                <p className="text-[13.5px] font-medium">Drop files here</p>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {system.data
                    ? `${system.data.accepted_extensions.join(" ")} up to ${system.data.max_upload_mb} MB, 20 at a time`
                    : "PDF, Word, Markdown, HTML, text and CSV"}
                </p>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="mt-3"
                  onClick={() => input.current?.click()}
                >
                  Choose files
                </Button>
                <input
                  ref={input}
                  type="file"
                  multiple
                  accept={accept}
                  className="sr-only"
                  aria-label="Choose files"
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
              </div>
              {files.length ? (
                <ul className="border-border divide-border max-h-36 divide-y overflow-y-auto rounded-lg border text-[13px]">
                  {files.map((file, index) => (
                    <li
                      key={`${file.name}-${index}`}
                      className="flex items-center gap-2 px-3 py-1.5"
                    >
                      <span className="min-w-0 flex-1 truncate">{file.name}</span>
                      <span className="text-subtle tabular text-xs">{formatBytes(file.size)}</span>
                      <button
                        type="button"
                        aria-label={`Remove ${file.name}`}
                        className="text-subtle hover:text-foreground rounded p-0.5"
                        onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                      >
                        <X className="size-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <MetadataField id="files-metadata" value={metadata} onChange={setMetadata} />
            </TabsContent>
            <TabsContent value="text" className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_9rem]">
                <div className="space-y-1.5">
                  <Label htmlFor="text-title">Title</Label>
                  <Input id="text-title" value={title} onChange={(e) => setTitle(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="text-format">Format</Label>
                  <NativeSelect
                    id="text-format"
                    value={format}
                    onChange={(e) => setFormat(e.target.value as "markdown" | "text")}
                  >
                    <option value="markdown">Markdown</option>
                    <option value="text">Plain text</option>
                  </NativeSelect>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="text-body">Text</Label>
                <Textarea
                  id="text-body"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="min-h-36"
                  placeholder={"# Refund policy\n\nRefunds are available for 180 days..."}
                />
              </div>
              <MetadataField id="text-metadata" value={metadata} onChange={setMetadata} />
            </TabsContent>
            <TabsContent value="urls" className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="urls">Addresses</Label>
                <Textarea
                  id="urls"
                  value={urls}
                  onChange={(e) => setUrls(e.target.value)}
                  className="min-h-28 font-mono text-[12.5px]"
                  placeholder="https://docs.example.com/guides/webhooks"
                />
                <FieldHint>
                  One per line. Pages are fetched by the worker; private network addresses are
                  refused.
                </FieldHint>
              </div>
              <MetadataField id="urls-metadata" value={metadata} onChange={setMetadata} />
            </TabsContent>
          </Tabs>
          {problem ? <ErrorNotice message={problem} /> : null}
          {rejected.length ? (
            <div
              className="border-warning/30 bg-warning-soft text-warning rounded-lg border px-3 py-2 text-[13px]"
              role="status"
            >
              <p className="font-medium">Some sources were not added:</p>
              <ul className="mt-1 list-disc pl-5">
                {rejected.map((item) => (
                  <li key={`${item.name}-${item.code}`}>
                    {item.name}: {item.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!ready || pending}>
              {pending ? "Adding..." : "Add"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
