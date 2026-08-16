/**
 * What Home puts in front of the employee, and in what role.
 *
 * Home answers three questions in order: what is happening with my workday, is
 * anything waiting for me, and what can I do right now. Everything below decides
 * which single item earns the action emphasis; colour follows that role rather
 * than the owning module, so the page never rotates hues by list position.
 */
import type { HomeDestination, HomeTask } from '@/composition/employeeAppComposition'

export type PriorityTone = 'action' | 'calm'

export type HomeActionPlan = {
  /** The onboarding journey owns the action slot while it is running. */
  showOnboarding: boolean
  /** Otherwise the one task the employee must act on, if there is one. */
  actionTask: HomeTask | null
  /** Everything else stays a compact row. */
  secondaryTasks: HomeTask[]
}

/**
 * One filled emphasis, never two.
 *
 * Onboarding outranks a task because it carries the count and the call to
 * action together. Informational work earns no card at all: a payslip that was
 * released is worth a row, and painting it like an obligation is a lie told in
 * colour.
 */
export function planHomeActions(args: {
  showOnboarding: boolean
  tasks: HomeTask[]
}): HomeActionPlan {
  const { showOnboarding, tasks } = args

  if (showOnboarding) {
    return { showOnboarding: true, actionTask: null, secondaryTasks: tasks }
  }

  const actionTask = tasks.find((task) => task.severity === 'action_required') ?? null
  return {
    showOnboarding: false,
    actionTask,
    secondaryTasks: actionTask ? tasks.filter((task) => task.id !== actionTask.id) : tasks,
  }
}

/**
 * Destinations the employee still needs to discover on Home.
 *
 * When the yellow priority already opens documents work (renewal or onboarding),
 * a second Documents launcher under it is noise. Other destinations still show.
 */
export function visibleHomeDestinations(
  destinations: HomeDestination[],
  plan: HomeActionPlan,
): HomeDestination[] {
  const documentsAlreadyOpened =
    plan.showOnboarding ||
    plan.actionTask?.kind === 'document_renewal' ||
    plan.actionTask?.kind === 'onboarding_documents'

  if (!documentsAlreadyOpened) return destinations
  return destinations.filter((destination) => destination.id !== 'documents')
}

/**
 * A quiet Home (one waiting surface or fewer, no discovery rows) leaves a long
 * cream field under the action cluster. Sparse mode grows the workday hero and
 * opens the page rhythm so that emptiness reads as designed margin — never by
 * inventing facts or floating the leave CTA to the tab bar.
 */
export function isSparseHomePage(args: {
  plan: HomeActionPlan
  destinationCount: number
  showCaughtUp: boolean
}): boolean {
  const waitingSurfaces =
    (args.plan.showOnboarding ? 1 : 0) +
    (args.plan.actionTask ? 1 : 0) +
    args.plan.secondaryTasks.length +
    (args.showCaughtUp ? 1 : 0) +
    args.destinationCount
  return waitingSurfaces <= 1
}

/** Ambient family for a Home role — yellow means "you must act", green means calm. */
export function ambientForPriorityTone(tone: PriorityTone) {
  return tone === 'action' ? ('onboarding' as const) : ('leave' as const)
}
