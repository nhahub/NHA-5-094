import { useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, ShieldCheck, UsersRound } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { api, ApiError } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { ProvisionableUserRole, UserRead } from "../../api/contracts";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Button, EmptyState, ErrorState, Field, LoadingState, PageHeader, SuccessNotice } from "../../components/Ui";

type ProvisionForm = {
  fullName: string;
  email: string;
  password: string;
  role: ProvisionableUserRole;
};

const blankForm: ProvisionForm = { fullName: "", email: "", password: "", role: "EMPLOYEE" };
const EMPTY_USERS: UserRead[] = [];

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "The request could not be completed. Try again.";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

export function UsersPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const formRef = useRef<HTMLFormElement>(null);
  const [query, setQuery] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<ProvisionForm>(blankForm);
  const [success, setSuccess] = useState<string | null>(null);
  const usersQuery = useQuery({
    queryKey: queryKeys.organizationUsers(user),
    queryFn: () => api.auth.users(),
    enabled: user?.role === "ADMIN",
  });
  const provisionMutation = useMutation({
    mutationFn: api.auth.provisionUser,
    onSuccess: async (created) => {
      setSuccess(`${created.full_name} was added to this organization.`);
      setCreateOpen(false);
      setForm(blankForm);
      await queryClient.invalidateQueries({ queryKey: queryKeys.organizationUsers(user) });
    },
  });

  const users = usersQuery.data ?? EMPTY_USERS;
  const filteredUsers = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    if (!term) return users;
    return users.filter((item) => `${item.full_name} ${item.email} ${item.role}`.toLocaleLowerCase().includes(term));
  }, [query, users]);

  function submitUser(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!formRef.current?.reportValidity()) return;
    setSuccess(null);
    provisionMutation.mutate({
      full_name: form.fullName.trim(),
      email: form.email.trim(),
      password: form.password,
      role: form.role,
    });
  }

  function closeCreate() {
    if (provisionMutation.isPending) return;
    setCreateOpen(false);
    setForm(blankForm);
    provisionMutation.reset();
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="ORGANIZATION ADMINISTRATION"
        title="User access"
        description="Review accounts in your organization and provision non-administrator roles."
        actions={<Button icon={<Plus size={17} aria-hidden="true" />} onClick={() => { setSuccess(null); setCreateOpen(true); }}>Add user</Button>}
      />

      {success && <SuccessNotice>{success} Share the initial password through your approved secure channel.</SuccessNotice>}
      {usersQuery.isError && !usersQuery.data && <ErrorState message={errorText(usersQuery.error)} onRetry={() => void usersQuery.refetch()} />}

      <section className="panel user-access-panel" aria-labelledby="organization-users-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">DIRECTORY</p>
            <h2 id="organization-users-title">Organization users</h2>
            <p>Showing accounts returned for your organization, up to 100 records.</p>
          </div>
          <span className="user-record-count"><UsersRound size={16} aria-hidden="true" />{usersQuery.isPending ? "—" : filteredUsers.length} shown</span>
        </div>

        <label className="search-control user-search">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Search organization users</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, email, or role" />
        </label>

        {usersQuery.isPending ? (
          <LoadingState label="Loading organization users" />
        ) : usersQuery.isError ? (
          usersQuery.data ? <div className="partial-data-note" role="status">The directory could not be refreshed. Displayed results may be out of date.</div> : null
        ) : users.length === 0 ? (
          <EmptyState title="No users were returned" description="The authenticated account could not find any user records in this organization." icon={<UsersRound size={22} aria-hidden="true" />} />
        ) : filteredUsers.length === 0 ? (
          <EmptyState title="No matching users" description="Try another name, email address, or role." icon={<Search size={22} aria-hidden="true" />} />
        ) : (
          <div className="table-scroll">
            <table className="data-table user-table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Account status</th>
                  <th scope="col">Created</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((item) => (
                  <tr key={item.id}>
                    <td><strong className="user-name-cell">{item.full_name}</strong></td>
                    <td>{item.email}</td>
                    <td><span className="role-pill">{item.role}</span></td>
                    <td><span className={`account-status ${item.is_active ? "account-status-active" : "account-status-inactive"}`}><span aria-hidden="true" />{item.is_active ? "Active" : "Inactive"}</span></td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="user-directory-note"><ShieldCheck size={15} aria-hidden="true" /> User access is organization-scoped and enforced by the API. This screen cannot create administrator accounts or change account activation.</p>
      </section>

      <ConfirmDialog
        open={createOpen}
        title="Provision an organization user"
        description="Choose a role and a strong initial password. The account is created inside your organization and becomes active immediately."
        confirmLabel="Create user"
        confirmDisabled={provisionMutation.isPending || form.fullName.trim().length < 2 || !form.email.trim() || form.password.length < 15}
        busy={provisionMutation.isPending}
        onConfirm={() => submitUser()}
        onClose={closeCreate}
      >
        <form ref={formRef} className="dialog-form user-provision-form" onSubmit={submitUser}>
          {provisionMutation.isError && <div className="field-error" role="alert">{errorText(provisionMutation.error)}</div>}
          <Field id="provision-name" label="Full name">
            <input id="provision-name" autoComplete="name" maxLength={255} required minLength={2} value={form.fullName} onChange={(event) => setForm((current) => ({ ...current, fullName: event.target.value }))} />
          </Field>
          <Field id="provision-email" label="Work email">
            <input id="provision-email" type="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" required value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} />
          </Field>
          <Field id="provision-role" label="Role" hint="Administrator access cannot be assigned from this screen.">
            <select id="provision-role" value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value as ProvisionableUserRole }))}>
              <option value="EMPLOYEE">Employee</option>
              <option value="MANAGER">Manager</option>
              <option value="CUSTOMER">Customer</option>
            </select>
          </Field>
          <Field id="provision-password" label="Initial password" hint="Use at least 15 characters and no more than 72 UTF-8 bytes. Share it only through an approved secure channel.">
            <input id="provision-password" type="password" autoComplete="new-password" minLength={15} maxLength={72} required value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} />
          </Field>
        </form>
      </ConfirmDialog>
    </div>
  );
}
