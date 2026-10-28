import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, Search } from "lucide-react";
import { Link } from "react-router";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../../components/Ui";

const TASK_STATUSES = ["PENDING", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "REJECTED", "CANCELLED"];
const EMPTY_TASKS: Awaited<ReturnType<typeof api.tasks.mine>> = [];

export function TasksPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const tasksQuery = useQuery({
    queryKey: queryKeys.myTasks(user),
    queryFn: api.tasks.mine,
    enabled: Boolean(user),
  });
  const tasks = tasksQuery.data ?? EMPTY_TASKS;
  const visibleTasks = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return tasks.filter((task) => {
      const statusMatches = !status || task.status.toUpperCase() === status;
      const searchMatches = !needle || `${task.title} ${task.description ?? ""} ${task.case_id}`.toLowerCase().includes(needle);
      return statusMatches && searchMatches;
    });
  }, [tasks, status, search]);
  const openCount = tasks.filter((task) => !["COMPLETED", "REJECTED", "CANCELLED"].includes(task.status.toUpperCase())).length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="YOUR WORK"
        title="My tasks"
        description="Items returned for your user, role, or department by the backend task queue."
        actions={<span className="task-queue-count"><ClipboardCheck size={16} aria-hidden="true" />{openCount} open</span>}
      />
      <section className="panel">
        <div className="filter-toolbar">
          <div className="search-control">
            <Search size={17} aria-hidden="true" />
            <label className="sr-only" htmlFor="task-search">Search your assigned tasks</label>
            <input id="task-search" type="search" value={search} placeholder="Search assigned tasks" onChange={(event) => setSearch(event.target.value)} />
          </div>
          <div className="filter-select-wrap">
            <label className="sr-only" htmlFor="task-status">Filter by task status</label>
            <select id="task-status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              {TASK_STATUSES.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
            </select>
          </div>
        </div>

        {tasksQuery.isPending ? (
          <LoadingState label="Loading your tasks" />
        ) : tasksQuery.isError ? (
          <ErrorState message={getError(tasksQuery.error)} onRetry={() => void tasksQuery.refetch()} />
        ) : visibleTasks.length === 0 ? (
          <EmptyState
            title={search || status ? "No tasks match these filters" : "Your task queue is clear"}
            description={search || status ? "Clear a filter to see the rest of your assigned work." : "The backend will add tasks here when a case needs human work."}
            icon={<ClipboardCheck size={22} aria-hidden="true" />}
            action={search || status ? <Button variant="secondary" onClick={() => { setSearch(""); setStatus(""); }}>Clear filters</Button> : undefined}
          />
        ) : (
          <div className="task-list">
            {visibleTasks.map((task) => (
              <article className="task-list-card" key={task.id}>
                <div className="task-list-marker" aria-hidden="true"><ClipboardCheck size={18} /></div>
                <div className="task-list-main">
                  <div className="task-list-title-row"><div><strong>{task.title}</strong><span>{task.description || "No task description was provided."}</span></div><StatusBadge status={task.status} /></div>
                  <div className="task-list-meta"><span>{task.task_type} · {task.priority}</span><span>Task {task.id.slice(0, 8)}</span>{task.due_at && <span>Due {formatDate(task.due_at)}</span>}</div>
                </div>
                <Link className="button button-secondary task-open-link" to={`/cases/${task.case_id}?view=review`}>Review case</Link>
              </article>
            ))}
          </div>
        )}
      </section>
      <p className="case-source-note">Task assignment and resolution permissions are evaluated by the backend. If an action is unavailable, ask a manager to review the assignment.</p>
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function getError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}
