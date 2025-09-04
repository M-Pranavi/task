def call(Map args) {
  def isE2E = args.account ?: false

  def change = args.approval ?: false

  // Gather all accounts that match our criteria
  filteredAccounts = args.accounts.findAll(
    {it.value.provisionChangeApprovalRequired == change && args.region in it.value.regions}
  )

  //Add region to key and value
  filteredAccounts = filteredAccounts.collectEntries { key, val ->
    [(key + " (${args.region})"): val + [region: args.region]]
  }

  if (isE2E) {
    return filteredAccounts.findAll({it.value.id == args.account})
  }

  // Return all but the e2e account
  return filteredAccounts.findAll({it.value.id != end_to_end[args.env]})
}

return this
