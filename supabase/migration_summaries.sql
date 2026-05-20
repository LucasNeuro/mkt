-- Rode no SQL Editor do Supabase (se as tabelas ainda não existirem)

create table if not exists wa_sessions (
  id uuid primary key default gen_random_uuid(),
  instance_name text not null default 'RTEPORT_INSTANTANEO',
  admin_phone text not null,
  step text not null default 'idle',
  selected_group_jid text,
  selected_group_name text,
  pending_groups jsonb,
  updated_at timestamptz not null default now(),
  unique (instance_name, admin_phone)
);

create table if not exists wa_summaries (
  id uuid primary key default gen_random_uuid(),
  instance_name text not null default 'RTEPORT_INSTANTANEO',
  group_jid text not null,
  group_name text,
  summary_date date not null,
  content text not null,
  message_count int default 0,
  requested_by text,
  sent_to_group boolean default false,
  poll_sent boolean default false,
  created_at timestamptz not null default now(),
  unique (instance_name, group_jid, summary_date)
);

create index if not exists idx_wa_sessions_admin on wa_sessions (admin_phone);
create index if not exists idx_wa_summaries_group on wa_summaries (group_jid, summary_date desc);

alter table wa_sessions enable row level security;
alter table wa_summaries enable row level security;
