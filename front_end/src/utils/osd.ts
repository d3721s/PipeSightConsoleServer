export function formatWheelMileage(left: number | null | undefined, right: number | null | undefined): string {
  if (
    typeof left !== 'number' ||
    typeof right !== 'number' ||
    !Number.isFinite(left) ||
    !Number.isFinite(right)
  ) {
    return '--'
  }
  return `${left.toFixed(2)}m-${right.toFixed(2)}m`
}
