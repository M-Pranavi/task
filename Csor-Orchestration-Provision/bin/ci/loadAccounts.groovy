import org.braintree.csor.CsorClient

def call(String env) {
  def client = new CsorClient(this)
  def accounts = client.query(env, "bin/ci/query/accounts.graphql")

  def filteredAccounts = accounts.data.accounts.findAll { account ->
      account.appInfra.any { execution ->
          execution.lastSuccess?.deployers?.any { deployer ->
              deployer.outputs?.fargate_role_arn != null && deployer.outputs.fargate_role_arn != [:]
          }
      }
  }.collect { account ->
      [
          id: account.id,
          name: account.name,
          regions: account.appInfra*.region,
          provisionChangeApprovalRequired: account.provisionChangeApprovalRequired
      ]
  }

  def finalAccounts = [:]
  for (accountMap in filteredAccounts) {
    name = accountMap["name"]
    finalAccounts[name] = accountMap
  }
  println "finalAccounts"
  println finalAccounts
  return finalAccounts
}

return this
