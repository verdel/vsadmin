from pyVmomi import pbm, VmomiSupport, SoapStubAdapter

def PbmConnect(stubAdapter, disable_ssl_verification=False):
    """Connect to the VMware Storage Policy Server

    :param stubAdapter: The ServiceInstance stub adapter
    :type stubAdapter: SoapStubAdapter
    :param disable_ssl_verification: A flag used to skip ssl certificate
        verification (default is False)
    :type disable_ssl_verification: bool
    :returns: A VMware Storage Policy Service content object
    :rtype: ServiceContent
    """

    if disable_ssl_verification:
        import ssl
        if hasattr(ssl, '_create_unverified_context'):
            sslContext = ssl._create_unverified_context()
        else:
            sslContext = None
    else:
        sslContext = None

    VmomiSupport.GetRequestContext()["vcSessionCookie"] = \
        stubAdapter.cookie.split('"')[1]
    hostname = stubAdapter.host.split(":")[0]
    pbmStub = SoapStubAdapter(
        host=hostname,
        version="pbm.version.version1",
        path="/pbm/sdk",
        poolSize=0,
        sslContext=sslContext)
    pbmSi = pbm.ServiceInstance("ServiceInstance", pbmStub)
    pbmContent = pbmSi.RetrieveContent()
    return pbmContent


def GetStorageProfiles(profileManager, ref):
    """Get vmware storage policy profiles associated with specified entities

    :param profileManager: A VMware Storage Policy Service manager object
    :type profileManager: pbm.profile.ProfileManager
    :param ref: A server reference to a virtual machine, virtual disk,
        or datastore
    :type ref: pbm.ServerObjectRef
    :returns: A list of VMware Storage Policy profiles associated with
        the specified entities
    :rtype: pbm.profile.Profile[]
    """

    profiles = []
    profileIds = profileManager.PbmQueryAssociatedProfile(ref)
    if len(profileIds) > 0:
        profiles = profileManager.PbmRetrieveContent(profileIds=profileIds)
        return profiles
    return profiles


def ShowStorageProfileCapabilities(capabilities):
    """Print vmware storage policy profile capabilities

    :param capabilities: A list of VMware Storage Policy profile
        associated capabilities
    :type capabilities: pbm.capability.AssociatedPolicyCapabilities
    :returns: str
    """
    result = ""
    for capability in capabilities:
        for constraint in capability.constraint:
            if hasattr(constraint, 'propertyInstance'):
                for propertyInstance in constraint.propertyInstance:
                    result += "                                     Parameter: {} Value: {}\r\n".format(propertyInstance.id,
                                                                                                    propertyInstance.value)
    return result


def ShowStorageProfile(profiles, verbose=False):
    """Print vmware storage policy profile

    :param profiles: A list of VMware Storage Policy profiles
    :type profiles: pbm.profile.Profile[]
    :returns: str
    """
    result = ""
    if len(profiles) > 0:
        for profile in profiles:
            result += "Name: {} \r\n".format(profile.name)
            if verbose:
                result += "                                     Description: {} \r\n".format(profile.description)
            if hasattr(profile.constraints, 'subProfiles') and verbose:
                subprofiles = profile.constraints.subProfiles
                for subprofile in subprofiles:
                    capabilities = subprofile.capability
                    result += ShowStorageProfileCapabilities(capabilities)
    else:
        result += "Name: Datastore Default \r\n"
    return result
