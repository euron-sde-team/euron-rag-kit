"use client";

import { FolderPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Wordmark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/feedback";
import { Input, Label, Textarea } from "@/components/ui/input";
import { useCreateProject } from "@/lib/queries";
import { runtimeEnv } from "@/lib/runtime-env";

export default function WelcomePage() {
  const router = useRouter();
  const create = useCreateProject();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const project = await create.mutateAsync({ name, description });
    router.replace(`/p/${project.slug}/collections`);
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-8 p-6">
      <Wordmark name={runtimeEnv().productName} />
      <Card className="w-full max-w-md p-6">
        <div className="mb-5 flex items-center gap-3">
          <span className="bg-accent text-accent-foreground flex size-10 items-center justify-center rounded-xl">
            <FolderPlus className="size-5" />
          </span>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Create a project</h1>
            <p className="text-muted-foreground text-[13px]">
              A project holds collections, evaluation datasets, API keys and the people who use
              them.
            </p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Docs assistant"
              required
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-description">Description</Label>
            <Textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What will this retrieval serve?"
            />
          </div>
          {create.error ? <ErrorNotice message={create.error.message} /> : null}
          <Button type="submit" className="w-full" disabled={!name.trim() || create.isPending}>
            Create project
          </Button>
        </form>
      </Card>
    </main>
  );
}
