"use client";

import { Check, ChevronsUpDown, Plus, Settings } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ErrorNotice } from "@/components/ui/feedback";
import { Input, Label, Textarea } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";
import { useCreateProject } from "@/lib/queries";
import type { ProjectSummary } from "@/lib/types";

export function ProjectAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      className={cn(
        "bg-primary text-primary-foreground flex size-7 shrink-0 items-center justify-center rounded-lg text-[11px] font-semibold",
        className,
      )}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

export function ProjectSwitcher({
  current,
  all,
}: {
  current: ProjectSummary;
  all: ProjectSummary[];
}) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="hover:bg-muted flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors"
            aria-label="Switch project"
          >
            <ProjectAvatar name={current.name} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13.5px] leading-tight font-semibold">
                {current.name}
              </span>
              <span className="text-muted-foreground block text-[11.5px] capitalize">
                {current.role}
              </span>
            </span>
            <ChevronsUpDown className="text-subtle size-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuLabel>Projects</DropdownMenuLabel>
          {all.map((project) => (
            <DropdownMenuItem key={project.id} onSelect={() => router.push(`/p/${project.slug}`)}>
              <ProjectAvatar name={project.name} className="size-6 text-[10px]" />
              <span className="min-w-0 flex-1 truncate">{project.name}</span>
              {project.id === current.id ? <Check className="!text-primary" /> : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCreating(true)}>
            <Plus /> Create project
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href={`/p/${current.slug}/settings`}>
              <Settings /> Project settings
            </Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <CreateProjectDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}

function CreateProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const create = useCreateProject();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const project = await create.mutateAsync({ name, description });
    onOpenChange(false);
    setName("");
    setDescription("");
    router.push(`/p/${project.slug}/collections`);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Create a project"
        description="Projects keep collections, datasets, keys and members separate."
      >
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="new-project-name">Name</Label>
            <Input
              id="new-project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-project-description">Description</Label>
            <Textarea
              id="new-project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {create.error ? <ErrorNotice message={create.error.message} /> : null}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
