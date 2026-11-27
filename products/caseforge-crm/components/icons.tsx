
import { createElement } from "react";
import type { SVGProps } from "react";
import { LUCIDE_ICON_NODES } from "@/lib/lucideIconNodes";

function LucideIcon({ name, ...props }: SVGProps<SVGSVGElement> & { name: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"

      width="1em"
      height="1em"
      {...props}
    >
      {LUCIDE_ICON_NODES[name].map(([tag, attrs], index) => createElement(tag, { key: index, ...attrs }))}
    </svg>
  );
}

export function IconSortAZ(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="arrow-down-a-z" {...props} />;
}

export function IconEye(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="eye" {...props} />;
}

export function IconEyeOff(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="eye-off" {...props} />;
}

export function IconSearch(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="search" {...props} />;
}

export function IconSun({ filled = false, ...props }: SVGProps<SVGSVGElement> & { filled?: boolean }) {
  return <LucideIcon name="sun" fill={filled ? "currentColor" : "none"} {...props} />;
}

export function IconMoon(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="moon" {...props} />;
}

export function IconSystem(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="monitor" {...props} />;
}

export function IconApps(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="square-menu" {...props} />;
}

export function IconHome(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="house" {...props} />;
}

export function IconCopy(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="copy" {...props} />;
}

export function IconCheck(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="check" {...props} />;
}

export function IconClock(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="clock" {...props} />;
}

export function IconUserPlus(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="user-plus" {...props} />;
}

export function IconShield(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="shield" {...props} />;
}

export function IconShieldOff(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="shield-off" {...props} />;
}

export function IconPlaceholder(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="square" {...props} />;
}

export function IconCall(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="phone" {...props} />;
}

export function IconRefresh(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="refresh-cw" {...props} />;
}

export function IconSettings(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="settings" {...props} />;
}

export function IconCalendar(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="calendar-days" {...props} />;
}

export function IconChevronLeft(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="chevron-left" {...props} />;
}

export function IconChevronRight(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="chevron-right" {...props} />;
}

export function IconDownload(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="download" {...props} />;
}

export function IconPlus(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="plus" {...props} />;
}

export function IconMinus(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="minus" {...props} />;
}

export function IconPin({ filled = false, ...props }: SVGProps<SVGSVGElement> & { filled?: boolean }) {
  return <LucideIcon name="pin" fill={filled ? "currentColor" : "none"} {...props} />;
}

export function IconClose(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="x" {...props} />;
}

export function IconRegenerate(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="rotate-cw" {...props} />;
}

export function IconThumbUp(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="thumbs-up" {...props} />;
}

export function IconThumbDown(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="thumbs-down" {...props} />;
}

export function IconArrowUp(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="arrow-up" {...props} />;
}

export function IconStop(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="square" fill="currentColor" {...props} />;
}

export function IconAlert(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="triangle-alert" {...props} />;
}

export function IconBell(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="bell" {...props} />;
}

export function IconTray(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="inbox" {...props} />;
}

export function IconFace(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="frown" {...props} />;
}

export function IconSmile(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="smile" {...props} />;
}

export function IconPhoneRinging(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="phone-call" {...props} />;
}

export function IconShout(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="megaphone" {...props} />;
}

export function IconScan(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="printer" {...props} />;
}

export function IconPeople(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="users" {...props} />;
}

export function IconGraduationCap(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="graduation-cap" {...props} />;
}

export function IconMessage(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="message-square" {...props} />;
}

export function IconList(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="list" {...props} />;
}

export function IconRestore(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="archive-restore" {...props} />;
}

export function IconActivity(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="activity" {...props} />;
}

export function IconFunnel(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="funnel" {...props} />;
}

export function IconPound(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="pound-sterling" {...props} />;
}

export function IconSparkles(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="sparkles" {...props} />;
}

export function IconListChecks(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="list-checks" {...props} />;
}

export function IconBoard(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="kanban" {...props} />;
}

export function IconLock(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="lock" {...props} />;
}

export function IconFolder(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="folder" {...props} />;
}

export function IconStorage(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="hard-drive" {...props} />;
}

export function IconFolderOpen(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="folder-open" {...props} />;
}

export function IconFolderTree(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="folder-tree" {...props} />;
}

export function IconFile(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="file" {...props} />;
}

export function IconAuditLog(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="scroll-text" {...props} />;
}

export function IconTag(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="tag" {...props} />;
}

export function IconBellOff(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="bell-off" {...props} />;
}

export function IconHelp(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="circle-help" {...props} />;
}

export function IconEnvelope(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="mail" {...props} />;
}

export function IconLandmark(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="landmark" {...props} />;
}

export function IconPerson(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="user" {...props} />;
}

export function IconBot(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="bot" {...props} />;
}

export function IconAutomation(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="workflow" {...props} />;
}

export function IconFlag({ filled = false, ...props }: SVGProps<SVGSVGElement> & { filled?: boolean }) {
  return <LucideIcon name="flag" fill={filled ? "currentColor" : "none"} {...props} />;
}

export function IconStar({ filled = false, ...props }: SVGProps<SVGSVGElement> & { filled?: boolean }) {
  return <LucideIcon name="star" fill={filled ? "currentColor" : "none"} {...props} />;
}

export function IconDrawer({ open = false, ...props }: SVGProps<SVGSVGElement> & { open?: boolean }) {
  return <LucideIcon name="menu" data-open={open || undefined} {...props} />;
}

export function IconTrash(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="trash-2" {...props} />;
}

export function IconPencil(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="pencil" {...props} />;
}

export function IconPen(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="file-signature" {...props} />;
}

export function IconLocation(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="map-pin" {...props} />;
}

export function IconBundle(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="briefcase-business" {...props} />;
}

export function IconChevronDown(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="chevron-down" {...props} />;
}

export function IconExternalLink(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="external-link" {...props} />;
}

export function IconArrowLeft(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="arrow-left" {...props} />;
}

export function IconArrowRight(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="arrow-right" {...props} />;
}

export function IconArrowDown(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="arrow-down" {...props} />;
}

export function IconArrowUpDown(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="arrow-up-down" {...props} />;
}

export function IconCircleCheck(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="circle-check" {...props} />;
}

export function IconCircle(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="circle" {...props} />;
}

export function IconCircleDashed(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="circle-dashed" {...props} />;
}

export function IconCircleDot(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="circle-dot" {...props} />;
}

export function IconBan(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="ban" {...props} />;
}

export function IconDna(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="dna" {...props} />;
}

export function IconMerge(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="git-merge" {...props} />;
}

export function IconEdit(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="square-pen" {...props} />;
}

export function IconRemoveClient(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="user-x" {...props} />;
}

export function IconGrip(props: SVGProps<SVGSVGElement>) {
  return <LucideIcon name="grip-vertical" {...props} />;
}
