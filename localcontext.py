from geni.aggregate import FrameworkRegistry
from geni.aggregate.context import Context
from geni.aggregate.user import User

def buildContext ():
  framework = FrameworkRegistry.get("portal")()

  framework.cert = "/home/ivey/.ssl/geni_cert_portal.pem"
  framework.key = "/home/ivey/.ssl/geni_cert_portal.pem"

  user = User()
  user.name = "jivey"
  user.urn = "urn:publicid:IDN+ch.geni.net+user+jivey"
  user.addKey("/home/ivey/.ssh/geni_key_portal.pub")

  context = Context()
  context.addUser(user)
  context.cf = framework
  context.project = "SDN-basedRouting"

  return context